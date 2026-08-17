-- =====================================================================
-- Schema: test
-- Sandbox schema chứa dữ liệu giả lập (simulated) cho trading app
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS test;

-- ---------------------------------------------------------------------
-- Table: test.users
-- Lưu thông tin user đã đăng ký trading app (dữ liệu test)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test.users (
    -- id tự tăng, bắt đầu từ 1000
    id              BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1000 INCREMENT BY 1) PRIMARY KEY,

    -- timestamps: created_at set 1 lần khi insert, updated_at tự cập nhật qua trigger bên dưới
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    name            VARCHAR(255) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    -- address 3 cấp: tỉnh/thành phố -> xã/phường -> chi tiết (số nhà, đường...)
    address         JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- ----- các field bổ sung, gợi ý cho user của 1 trading app -----
    email           VARCHAR(255) NOT NULL,                 -- dùng để đăng nhập / liên hệ
    phone_number    VARCHAR(20),                           -- xác thực OTP, hỗ trợ
    date_of_birth   DATE,                                  -- kiểm tra độ tuổi hợp lệ để giao dịch
    national_id     VARCHAR(20),                            -- số CCCD/CMND, phục vụ KYC
    kyc_status      VARCHAR(20) NOT NULL DEFAULT 'pending', -- trạng thái xác minh danh tính
    risk_profile    VARCHAR(20),                            -- khẩu vị rủi ro nhà đầu tư
    account_tier    VARCHAR(20) NOT NULL DEFAULT 'basic',   -- hạng tài khoản (phí giao dịch, hạn mức...)
    referral_code   VARCHAR(20),                            -- mã giới thiệu
    last_login_at   TIMESTAMPTZ,                            -- lần đăng nhập gần nhất

    CONSTRAINT uq_users_email       UNIQUE (email),
    CONSTRAINT uq_users_national_id UNIQUE (national_id),

    CONSTRAINT chk_users_kyc_status CHECK (kyc_status IN ('pending', 'verified', 'rejected')),
    CONSTRAINT chk_users_risk_profile CHECK (
        risk_profile IS NULL OR risk_profile IN ('conservative', 'moderate', 'aggressive')
    ),
    CONSTRAINT chk_users_account_tier CHECK (account_tier IN ('basic', 'premium', 'vip')),

    -- bắt buộc address phải là object và có đủ 3 cấp
    CONSTRAINT chk_users_address_shape CHECK (
        jsonb_typeof(address) = 'object'
        AND address ? 'province'
        AND address ? 'ward'
        AND address ? 'detail'
    )
);

COMMENT ON TABLE test.users IS 'Bảng test: user đã đăng ký trading app';
COMMENT ON COLUMN test.users.address IS '3 cấp: {"province": "...", "ward": "...", "detail": "..."}';
COMMENT ON COLUMN test.users.kyc_status IS 'Trạng thái xác minh KYC: pending | verified | rejected';
COMMENT ON COLUMN test.users.risk_profile IS 'Khẩu vị rủi ro: conservative | moderate | aggressive';
COMMENT ON COLUMN test.users.account_tier IS 'Hạng tài khoản: basic | premium | vip';

-- ---------------------------------------------------------------------
-- Trigger: tự động set updated_at mỗi khi row được UPDATE
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION test.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON test.users;
CREATE TRIGGER trg_users_set_updated_at
    BEFORE UPDATE ON test.users
    FOR EACH ROW
    EXECUTE FUNCTION test.set_updated_at();

-- ---------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_is_active   ON test.users (is_active);
CREATE INDEX IF NOT EXISTS idx_users_address_gin ON test.users USING GIN (address);

-- ---------------------------------------------------------------------
-- Sample seed data (10 rows, tuỳ chọn, có thể xoá nếu không cần)
-- ---------------------------------------------------------------------
INSERT INTO test.users (
    name, is_active, address, email, phone_number, date_of_birth,
    national_id, kyc_status, risk_profile, account_tier, referral_code, last_login_at
)
VALUES
    ('Nguyen Van A', TRUE,
     '{"province": "Ho Chi Minh", "ward": "Phuong Ben Nghe", "detail": "12 Nguyen Hue"}'::jsonb,
     'a.nguyen@example.com', '0901234567', '1995-05-20', '079095000123',
     'verified', 'moderate', 'premium', 'REF1000', now() - INTERVAL '2 hours'),

    ('Tran Thi B', TRUE,
     '{"province": "Ha Noi", "ward": "Phuong Cua Dong", "detail": "45 Hang Bong"}'::jsonb,
     'b.tran@example.com', '0912345678', '1998-11-03', '001098012345',
     'verified', 'conservative', 'basic', 'REF1001', now() - INTERVAL '1 day'),

    ('Le Van C', TRUE,
     '{"province": "Da Nang", "ward": "Phuong Thanh Khe Dong", "detail": "78 Dien Bien Phu"}'::jsonb,
     'c.le@example.com', '0923456789', '2000-02-14', '048200004321',
     'pending', 'aggressive', 'basic', 'REF1002', now() - INTERVAL '5 days'),

    ('Pham Thi D', TRUE,
     '{"province": "Ho Chi Minh", "ward": "Phuong Vo Thi Sau", "detail": "9 Nguyen Dinh Chieu"}'::jsonb,
     'd.pham@example.com', '0934567890', '1990-07-30', '079090007654',
     'verified', 'moderate', 'vip', 'REF1003', now() - INTERVAL '3 hours'),

    ('Hoang Van E', FALSE,
     '{"province": "Can Tho", "ward": "Phuong An Hoa", "detail": "23 Nguyen Van Cu"}'::jsonb,
     'e.hoang@example.com', '0945678901', '1993-09-09', '092093009876',
     'rejected', NULL, 'basic', 'REF1004', now() - INTERVAL '60 days'),

    ('Vu Thi F', TRUE,
     '{"province": "Hai Phong", "ward": "Phuong May To", "detail": "56 Dien Bien Phu"}'::jsonb,
     'f.vu@example.com', '0956789012', '1997-01-25', '031097005678',
     'verified', 'conservative', 'premium', 'REF1005', now() - INTERVAL '12 hours'),

    ('Dang Van G', FALSE,
     '{"province": "Ho Chi Minh", "ward": "Phuong Tan Dinh", "detail": "3 Hai Ba Trung"}'::jsonb,
     'g.dang@example.com', '0967890123', '2001-04-18', '079001004567',
     'pending', NULL, 'basic', 'REF1006', NULL),

    ('Bui Thi H', TRUE,
     '{"province": "Ha Noi", "ward": "Phuong Nghia Do", "detail": "101 Hoang Quoc Viet"}'::jsonb,
     'h.bui@example.com', '0978901234', '1988-12-12', '001088023456',
     'verified', 'aggressive', 'vip', 'REF1007', now() - INTERVAL '30 minutes'),

    ('Do Van I', TRUE,
     '{"province": "Nghe An", "ward": "Phuong Ha Huy Tap", "detail": "14 Le Loi"}'::jsonb,
     'i.do@example.com', '0989012345', '1996-06-06', '040096001234',
     'pending', 'moderate', 'basic', 'REF1008', now() - INTERVAL '7 days'),

    ('Ngo Thi K', TRUE,
     '{"province": "Ho Chi Minh", "ward": "Phuong Linh Trung", "detail": "200 Vo Van Ngan"}'::jsonb,
     'k.ngo@example.com', '0990123456', '1999-03-27', '079099009123',
     'verified', 'conservative', 'premium', 'REF1009', NULL)
-- Re-running pg-init against a volume that already has these rows must not
-- error out (that would abort setup.sh's automated run) -- skip rows that
-- already collide on email/national_id instead of failing on them.
ON CONFLICT DO NOTHING;

-- =====================================================================
-- CDC via WAL (logical decoding, wal2json plugin -- see simulated_app/Dockerfile)
-- Consumed with a plain SQL connection via pg_logical_slot_peek_changes() /
-- pg_replication_slot_advance() -- no pg_recvlogical, no Debezium/Kafka.
-- Guarded with existence checks so this stays safe to re-run (pg-init is
-- re-run on demand, and CREATE PUBLICATION / pg_create_logical_replication_slot
-- have no IF NOT EXISTS form).
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'cdc_users_pub') THEN
        CREATE PUBLICATION cdc_users_pub FOR TABLE test.users;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'cdc_users_slot') THEN
        PERFORM pg_create_logical_replication_slot('cdc_users_slot', 'wal2json');
    END IF;
END
$$;

-- NOTE: the slot only captures changes from this point forward. The 10 seed
-- rows above (and anything already in the table before the slot existed)
-- will NOT appear in the CDC stream -- ingest__tdb.py's first run should do
-- one full snapshot (SELECT * FROM test.users) as a baseline before relying
-- on the CDC export for incremental changes