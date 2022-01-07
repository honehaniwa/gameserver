import json
import uuid
from enum import Enum, IntEnum
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound

from .db import engine


class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げる"""


class SafeUser(BaseModel):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int

    class Config:
        orm_mode = True


class WaitRoomStatus(IntEnum):
    Waiting = 1
    LiveStart = 2
    Dissolution = 3


class RoomInfo(BaseModel):
    """Roomの情報を返す"""

    room_id: int
    live_id: int
    status: WaitRoomStatus
    joined_user_count: int
    max_user_count: int
    created_user_id: int

    class Config:
        orm_mode = True


class LiveDifficulty(IntEnum):
    normal = 1
    hard = 2


class RoomUser(BaseModel):
    """Room内のUserを格納"""

    user_id: int
    name: str
    leader_card_id: int
    select_difficulty: LiveDifficulty
    is_me: bool
    is_host: bool

    class Config:
        orm_mode = True


class ResultUser(BaseModel):
    """各UserのResultを格納"""

    user_id: int
    judge_count_list: list[int]
    score: int

    class Config:
        orm_mode = True


class JoinRoomResult(IntEnum):
    Ok = 1
    RoomFull = 2
    Disbanded = 3
    OtherError = 4


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    token = str(uuid.uuid4())
    # NOTE: tokenが衝突したらリトライする必要がある.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id) VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
    return token


def _get_user_by_token(conn, token: str) -> Optional[SafeUser]:
    result = conn.execute(
        text("SELECT `id`, `name`, `leader_card_id` FROM `user` WHERE `token`=:token"),
        dict(token=token),
    )
    try:
        row = result.one()
    except NoResultFound:
        return None
    return SafeUser.from_orm(row)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    # このコードを実装してもらう
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE `user` SET name=:name, leader_card_id=:leader_card_id WHERE token=:token"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
        # print(result)


def _join_room(
    conn, room_id: int, user_info: SafeUser, difficulty: LiveDifficulty
) -> None:
    room_info = get_room_info_from_id(conn, room_id)
    conn.execute(
        text(
            "INSERT INTO `room_member` (room_id, user_id, select_difficulty, is_host) VALUES (:room_id, :user_id, :select_difficulty, :is_host)"
        ),
        {
            "room_id": room_id,
            "user_id": user_info.id,
            "select_difficulty": difficulty.value,
            "is_host": room_info.created_user_id == user_info.id,
        },
    )

    conn.execute(
        text(
            "UPDATE `room` SET joined_user_count=:joined_user_count WHERE room_id=:room_id"
        ),
        {
            "joined_user_count": room_info.joined_user_count + 1,
            "room_id": room_id,
        },
    )


def _create_room(conn, user_info: SafeUser, live_id: int) -> int:
    result = conn.execute(
        text(
            "INSERT INTO `room` (live_id, status, created_user_id) VALUES (:live_id, :status, :created_user_id)"
        ),
        {"live_id": live_id, "status": 1, "created_user_id": user_info.id},
    )

    print(result.lastrowid)
    return result.lastrowid


def create_room(user_info: SafeUser, live_id: int, difficulty: LiveDifficulty) -> int:
    with engine.begin() as conn:
        room_id = _create_room(conn, user_info, live_id)
        _join_room(conn, room_id, user_info, difficulty)

        return room_id


def _room_list(conn, live_id: int) -> list[RoomInfo]:
    result = (
        conn.execute(
            text(
                "SELECT `room_id`, `live_id`, `status`, `joined_user_count`, `max_user_count`, `created_user_id` FROM `room` WHERE `live_id`=:live_id"
            ),
            dict(live_id=live_id),
        )
        if live_id != 0
        else conn.execute(
            text(
                "SELECT `room_id`, `live_id`, `status`, `joined_user_count`, `max_user_count`, `created_user_id` FROM `room`"
            ),
            dict(live_id=live_id),
        )
    )

    room_info_list = [RoomInfo.from_orm(row) for row in result.all()]

    return room_info_list


def room_list(live_id: int) -> list[RoomInfo]:
    with engine.begin() as conn:
        return _room_list(conn, live_id)


def get_room_info_from_id(conn, room_id: int) -> RoomInfo:
    print("get_room_info_from_id", room_id)
    result = conn.execute(
        text(
            "SELECT `room_id`, `live_id`, `status`, `joined_user_count`, `max_user_count`, `created_user_id` FROM `room` WHERE `room_id`=:room_id"
        ),
        dict(room_id=room_id),
    )
    try:
        row = result.one()
        print("get_room_info_from_id:", row)
    except Exception as e:
        print(e)
        return None
    return RoomInfo.from_orm(row)


def join_room(
    user_info: SafeUser, room_id: int, selected_difficulty: LiveDifficulty
) -> JoinRoomResult:
    with engine.begin() as conn:
        # room に入れるかを見る
        room = get_room_info_from_id(conn, room_id)
        if room.joined_user_count < room.max_user_count:
            # 人数がMAXに到達してないので入る
            _join_room(conn, room_id, user_info, selected_difficulty)
            return JoinRoomResult.Ok
        elif room.joined_user_count >= room.max_user_count:
            return JoinRoomResult.RoomFull
        elif room is None:
            return JoinRoomResult.Disbanded
        else:
            return JoinRoomResult.OtherError


def _get_joined_users(conn, room_id, user_id: int) -> list[RoomUser]:
    result = conn.execute(
        text(
            "SELECT `user_id`, `name`, `leader_card_id`, `select_difficulty`, `is_host` FROM `room_member` JOIN `user` ON room_member.user_id = user.id WHERE room_id=:room_id"
        ),
        dict(room_id=room_id),
    )
    print(result.all())
    joined_users = [
        RoomUser(
            user_id=row[0],
            name=row[1],
            leader_card_id=row[2],
            select_difficulty=row[3],
            is_me=user_id == row[0],
            is_host=row[4],
        )
        for row in result.all()
    ]

    return joined_users


def wait_room(user: SafeUser, room_id: int):
    with engine.begin() as conn:
        room = get_room_info_from_id(conn, room_id)
        if room is None:
            return None, None

        user_list = _get_joined_users(conn, room_id, user.id)

        return room.status, user_list
