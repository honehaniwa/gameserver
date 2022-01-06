DROP TABLE IF EXISTS `user`;
DROP TABLE IF EXISTS `room`;
DROP TABLE IF EXISTS `room_member`;
CREATE TABLE `user` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `token` varchar(255) DEFAULT NULL,
  `leader_card_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`)
);

CREATE TABLE `room` (
  `room_id` bigint NOT NULL AUTO_INCREMENT,
  `live_id` int NOT NULL,
  `joined_user_count` int DEFAULT 1,
  `max_user_count` int DEFAULT 4,
  `created_user_id` bigint NOT NULL,
  PRIMARY KEY (`room_id`)
);

CREATE TABLE `room_member` (
  `room_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `select_difficulty` int DEFAULT NULL,
  PRIMARY KEY (`room_id`),
  UNIQUE KEY `room_id` (`room_id`)
);