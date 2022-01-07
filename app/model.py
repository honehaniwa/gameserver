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


class RoomInfo(BaseModel):
    """Roomの情報を返す"""

    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int

    class Config:
        orm_mode = True


class LiveDifficulty(IntEnum):
    normal = 1
    hard = 2


class JoinRoomResult(IntEnum):
    Ok = 1
    RoomFull = 2
    Disbanded = 3
    OtherError = 4


class WaitRoomStatus(IntEnum):
    Waiting = 1
    LiveStart = 2
    Dissolution = 3


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    token = str(uuid.uuid4())
    # NOTE: tokenが衝突したらリトライする必要がある.
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id) VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
        # print(result)
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


def _join_room(conn, room_id: int, user_info: SafeUser, difficulty: LiveDifficulty) -> None:
    conn.execute(
        text(
            "INSERT INTO `room_member` (room_id, user_id, select_difficulty) VALUES (:room_id, :user_id, :select_difficulty)"
        ),
        {
            "room_id": room_id,
            "user_id": user_info.id,
            "select_difficulty": difficulty.value,
        },
    )

    conn.execute(
        text(
            "UPDATE `room` SET join_user_count=:name"
        ),
        {
            "room_id": room_id,
            "user_id": user_info.id,
            "select_difficulty": difficulty.value,
        },
    )


def _create_room(conn, user_info: SafeUser, live_id: int) -> int:
    result = conn.execute(
        text(
            "INSERT INTO `room` (live_id, created_user_id) VALUES (:live_id, :ceated_user_id)"
        ),
        {"live_id": live_id, "ceated_user_id": user_info.id},
    )

    print(result.lastrowid)
    return result.lastrowid


def create_room(user_info:  SafeUser, live_id: int, difficulty: LiveDifficulty) -> int:
    with engine.begin() as conn:
        room_id = _create_room(conn, user_info, live_id)
        _join_room(conn, room_id, user_info, difficulty)

        return room_id


def _room_list(conn, live_id: int) -> list[RoomInfo]:
    result = conn.execute(
        text(
            "SELECT `room_id`, `live_id`, `joined_user_count`, `max_user_count` FROM `room` WHERE `live_id`=:live_id"
        ),
        dict(live_id=live_id),
    )

    room_info_list = []
    for row in result.all():
        room_info_list.join(RoomInfo.from_orm(row))
    return room_info_list


def room_list(live_id: int) -> list[RoomInfo]:
    with engine.begin() as conn:
        return _room_list(conn, live_id)


def get_room_status_from_id(conn, room_id: int) -> RoomInfo:
    result = conn.execute(
        text(
            "SELECT `room_id`, `live_id`, `joined_user_count`, `max_user_count` FROM `room` WHERE `room_id`=:room_id"
        ),
        dict(room_id=room_id),
    )
    try:
        row = result.one()
    except Exception as e:
        print(e)
    return RoomInfo.from_orm(row)


def join_room(user_info: SafeUser, room_id: int, selected_difficulty: LiveDifficulty) -> JoinRoomResult:
    with engine.begin() as conn:
