CREATE TABLE IF NOT EXISTS users(
 id BIGSERIAL PRIMARY KEY, tg_id BIGINT UNIQUE NOT NULL, username TEXT, first_name TEXT,
 is_host BOOLEAN DEFAULT FALSE, is_banned BOOLEAN DEFAULT FALSE, created TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS global_channels(
 id BIGSERIAL PRIMARY KEY, chat_id BIGINT UNIQUE NOT NULL, title TEXT, link TEXT, active BOOLEAN DEFAULT TRUE);
CREATE TABLE IF NOT EXISTS giveaways(
 id BIGSERIAL PRIMARY KEY, host BIGINT NOT NULL, title TEXT NOT NULL, prize TEXT NOT NULL,
 description TEXT DEFAULT '', ends TIMESTAMPTZ NOT NULL, winners INT NOT NULL DEFAULT 1,
 status TEXT DEFAULT 'active', chat_id BIGINT, chat_target INT DEFAULT 0,
 bio_bonus TEXT DEFAULT '', name_bonus TEXT DEFAULT '', referral_bonus INT DEFAULT 1,
 referral_cap INT DEFAULT 20, discovery_msg BIGINT, created TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS giveaway_channels(
 id BIGSERIAL PRIMARY KEY, giveaway BIGINT REFERENCES giveaways(id) ON DELETE CASCADE,
 chat_id BIGINT NOT NULL, title TEXT, link TEXT NOT NULL, channel_type TEXT DEFAULT 'public',
 reward INT DEFAULT 1, required BOOLEAN DEFAULT TRUE,
 UNIQUE(giveaway, chat_id));
CREATE TABLE IF NOT EXISTS participants(
 id BIGSERIAL PRIMARY KEY, giveaway BIGINT REFERENCES giveaways(id) ON DELETE CASCADE,
 user_id BIGINT NOT NULL, joined TIMESTAMPTZ DEFAULT now(), captcha BOOLEAN DEFAULT FALSE,
 messages INT DEFAULT 0, last_count TIMESTAMPTZ, bonus INT DEFAULT 0, referral_entries INT DEFAULT 0,
 total_entries INT DEFAULT 1, valid BOOLEAN DEFAULT TRUE,
 UNIQUE(giveaway, user_id));
CREATE TABLE IF NOT EXISTS counted_messages(
 giveaway BIGINT, chat_id BIGINT, message_id BIGINT, user_id BIGINT,
 PRIMARY KEY(giveaway, chat_id, message_id));
CREATE TABLE IF NOT EXISTS referrals(
 id BIGSERIAL PRIMARY KEY, giveaway BIGINT REFERENCES giveaways(id) ON DELETE CASCADE,
 referrer BIGINT, invited BIGINT, valid BOOLEAN DEFAULT FALSE, created TIMESTAMPTZ DEFAULT now(),
 UNIQUE(giveaway, invited));
CREATE TABLE IF NOT EXISTS winners(
 id BIGSERIAL PRIMARY KEY, giveaway BIGINT REFERENCES giveaways(id) ON DELETE CASCADE,
 user_id BIGINT, round INT DEFAULT 1, selection TEXT DEFAULT 'random', reason TEXT, created TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS audit(
 id BIGSERIAL PRIMARY KEY, action TEXT, actor BIGINT, giveaway BIGINT, details TEXT, created TIMESTAMPTZ DEFAULT now());
