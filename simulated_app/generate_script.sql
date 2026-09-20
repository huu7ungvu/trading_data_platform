-- =====================================================================
-- Schema: tdb
-- Sandbox schema chứa cấu trúc dữ liệu giả lập (simulated) cho trading app
-- Init only: tạo schema/bảng/index/trigger. KHÔNG seed mock data ở đây.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS tdb;

-- ---------------------------------------------------------------------
-- Trigger function dùng chung: tự động set updated_at mỗi khi row UPDATE
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION tdb.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- Reference data
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table: tdb.companies
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.companies (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name            VARCHAR(255) NOT NULL,
    sector          VARCHAR(100),
    description     TEXT,
    website         VARCHAR(255),

    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_companies_status CHECK (status IN ('active', 'inactive', 'delisted'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.stocks
-- id = mã cổ phiếu (VNM, ACB, ...), không dùng surrogate key
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.stocks (
    id              VARCHAR(10) PRIMARY KEY,
    company_id      BIGINT NOT NULL REFERENCES tdb.companies (id),

    name            VARCHAR(255) NOT NULL,
    exchange        VARCHAR(20),   -- HOSE, HNX, UPCOM
    market_cap      BIGINT,
    sector          VARCHAR(100),

    min_price       DECIMAL(10,2),
    max_price       DECIMAL(10,2),
    min_lot_size    INT NOT NULL DEFAULT 1,
    price_tick      DECIMAL(10,4) NOT NULL DEFAULT 0.01,

    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_stocks_status CHECK (status IN ('active', 'suspended', 'delisted'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.banks
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.banks (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name            VARCHAR(100) NOT NULL,
    code            VARCHAR(20),
    country         VARCHAR(50),

    api_endpoint    VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_banks_name UNIQUE (name)
);

-- ---------------------------------------------------------------------
-- Table: tdb.addresses
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.addresses (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    street          VARCHAR(255),
    city            VARCHAR(100),
    province        VARCHAR(100),
    country         VARCHAR(100),
    postal_code     VARCHAR(20),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Table: tdb.fees
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.fees (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name                VARCHAR(100) NOT NULL,
    type                VARCHAR(30) NOT NULL,
    amount              DECIMAL(10,4),
    percentage          DECIMAL(5,4),

    applicable_to       VARCHAR(50),
    min_amount          DECIMAL(15,2),

    effective_from      DATE,
    effective_to        DATE,

    status              VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_fees_type CHECK (type IN ('TRADING_COMMISSION', 'WITHDRAWAL', 'DEPOSIT', 'MONTHLY')),
    CONSTRAINT chk_fees_status CHECK (status IN ('active', 'inactive', 'archived'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.promotions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.promotions (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name                    VARCHAR(255) NOT NULL,
    description             TEXT,
    type                    VARCHAR(30),

    discount_percent        DECIMAL(5,2),
    discount_amount         DECIMAL(15,2),
    max_discount            DECIMAL(15,2),

    applicable_to           VARCHAR(50),
    min_transaction_amount  DECIMAL(15,2),
    usage_limit_per_user    INT,

    valid_from              TIMESTAMPTZ,
    valid_to                TIMESTAMPTZ,

    status                  VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_promotions_type CHECK (type IS NULL OR type IN ('DISCOUNT', 'CASHBACK', 'BONUS', 'FREE_TRADE')),
    CONSTRAINT chk_promotions_status CHECK (status IN ('active', 'inactive', 'expired', 'archived'))
);

-- =====================================================================
-- Core entities
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table: tdb.users
-- wallet_id FK được thêm sau bằng ALTER (circular reference với wallets)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.users (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 1000 INCREMENT BY 1) PRIMARY KEY,

    email               VARCHAR(255) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    phone               VARCHAR(20),

    kyc_level           INT NOT NULL DEFAULT 0,   -- 0=not verified, 1=basic, 2=full
    identity_number     VARCHAR(50),

    address_id          BIGINT REFERENCES tdb.addresses (id),
    wallet_id           BIGINT,

    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    user_type           VARCHAR(20) NOT NULL DEFAULT 'individual',

    risk_profile        VARCHAR(20),
    daily_loss_limit    DECIMAL(15,2),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at       TIMESTAMPTZ,

    created_by          BIGINT,
    updated_by          BIGINT,

    CONSTRAINT uq_users_email           UNIQUE (email),
    CONSTRAINT uq_users_identity_number UNIQUE (identity_number),

    CONSTRAINT chk_users_status       CHECK (status IN ('active', 'suspended', 'banned', 'closed')),
    CONSTRAINT chk_users_user_type    CHECK (user_type IN ('individual', 'institutional')),
    CONSTRAINT chk_users_risk_profile CHECK (
        risk_profile IS NULL OR risk_profile IN ('conservative', 'moderate', 'aggressive')
    )
);

-- ---------------------------------------------------------------------
-- Table: tdb.wallets
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.wallets (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                     BIGINT NOT NULL REFERENCES tdb.users (id),

    balance                     DECIMAL(18,2) NOT NULL DEFAULT 0,
    currency                    VARCHAR(10) NOT NULL DEFAULT 'VND',

    status                      VARCHAR(20) NOT NULL DEFAULT 'active',

    daily_withdrawal_limit      DECIMAL(15,2),
    total_withdrawn_today       DECIMAL(15,2) NOT NULL DEFAULT 0,

    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_wallets_status CHECK (status IN ('active', 'frozen', 'closed'))
);

-- Close the circular reference now that tdb.wallets exists.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_wallet'
    ) THEN
        ALTER TABLE tdb.users
            ADD CONSTRAINT fk_users_wallet FOREIGN KEY (wallet_id) REFERENCES tdb.wallets (id);
    END IF;
END
$$;

-- =====================================================================
-- Bridge tables
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table: tdb.user_bank_linked
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.user_bank_linked (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id                 BIGINT NOT NULL REFERENCES tdb.users (id),
    bank_id                 BIGINT NOT NULL REFERENCES tdb.banks (id),

    account_number          VARCHAR(50) NOT NULL,
    account_holder_name     VARCHAR(255),
    account_type            VARCHAR(20),

    status                  VARCHAR(20) NOT NULL DEFAULT 'active',
    is_verified             BOOLEAN NOT NULL DEFAULT FALSE,

    linked_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at             TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_user_bank_linked UNIQUE (user_id, bank_id, account_number),
    CONSTRAINT chk_user_bank_linked_status CHECK (status IN ('active', 'inactive', 'unverified', 'deleted')),
    CONSTRAINT chk_user_bank_linked_account_type CHECK (
        account_type IS NULL OR account_type IN ('checking', 'savings')
    )
);

-- ---------------------------------------------------------------------
-- Table: tdb.user_fees
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.user_fees (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id         BIGINT NOT NULL REFERENCES tdb.users (id),
    fee_id          BIGINT NOT NULL REFERENCES tdb.fees (id),

    applied_from    DATE NOT NULL,
    applied_to      DATE,

    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_user_fees UNIQUE (user_id, fee_id, applied_from),
    CONSTRAINT chk_user_fees_status CHECK (status IN ('active', 'inactive', 'waived'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.user_promotions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.user_promotions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id         BIGINT NOT NULL REFERENCES tdb.users (id),
    promotion_id    BIGINT NOT NULL REFERENCES tdb.promotions (id),

    claimed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_count      INT NOT NULL DEFAULT 0,
    expires_at      TIMESTAMPTZ,

    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_user_promotions_status CHECK (status IN ('active', 'used', 'expired', 'revoked'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.user_stock_interests
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.user_stock_interests (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id         BIGINT NOT NULL REFERENCES tdb.users (id),
    stock_id        VARCHAR(10) NOT NULL REFERENCES tdb.stocks (id),

    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_viewed_at  TIMESTAMPTZ,
    view_count      INT NOT NULL DEFAULT 0,

    status          VARCHAR(20) NOT NULL DEFAULT 'active',

    CONSTRAINT uq_user_stock_interests UNIQUE (user_id, stock_id),
    CONSTRAINT chk_user_stock_interests_status CHECK (status IN ('active', 'removed'))
);

-- =====================================================================
-- Fact tables
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table: tdb.wallet_transactions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.wallet_transactions (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    wallet_id               BIGINT NOT NULL REFERENCES tdb.wallets (id),
    user_bank_linked_id     BIGINT REFERENCES tdb.user_bank_linked (id),   -- nullable: internal transfer

    type                    VARCHAR(20) NOT NULL,   -- DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT, FEE
    amount                  DECIMAL(18,2) NOT NULL,
    currency                VARCHAR(10) NOT NULL DEFAULT 'VND',

    status                  VARCHAR(20) NOT NULL DEFAULT 'pending',

    reference_number        VARCHAR(50),
    description             TEXT,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ,

    created_by              BIGINT,

    CONSTRAINT uq_wallet_transactions_reference UNIQUE (reference_number),
    CONSTRAINT chk_wallet_transactions_type CHECK (
        type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER_IN', 'TRANSFER_OUT', 'FEE')
    ),
    CONSTRAINT chk_wallet_transactions_status CHECK (status IN ('pending', 'completed', 'failed', 'reversed'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.orders
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.orders (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id                 BIGINT NOT NULL REFERENCES tdb.users (id),
    stock_id                VARCHAR(10) NOT NULL REFERENCES tdb.stocks (id),

    side                    VARCHAR(10) NOT NULL,   -- BUY, SELL
    quantity                INT NOT NULL,
    price                   DECIMAL(10,2) NOT NULL,
    order_type              VARCHAR(20) NOT NULL DEFAULT 'LIMIT',

    filled_quantity         INT NOT NULL DEFAULT 0,
    filled_price            DECIMAL(10,2),
    average_filled_price    DECIMAL(10,2),

    status                  VARCHAR(20) NOT NULL DEFAULT 'pending',

    order_date              DATE,
    order_time              TIME,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    filled_at               TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ,

    created_by              BIGINT,
    cancelled_by            BIGINT,
    cancellation_reason     VARCHAR(255),

    CONSTRAINT chk_orders_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_orders_order_type CHECK (order_type IN ('LIMIT', 'MARKET', 'STOP')),
    CONSTRAINT chk_orders_status CHECK (
        status IN ('pending', 'partially_filled', 'filled', 'cancelled', 'rejected', 'expired')
    )
);

-- ---------------------------------------------------------------------
-- Table: tdb.transactions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.transactions (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id             BIGINT NOT NULL REFERENCES tdb.users (id),
    wallet_id           BIGINT REFERENCES tdb.wallets (id),        -- nullable: non-wallet txns
    order_id            BIGINT REFERENCES tdb.orders (id),         -- nullable: non-trading txns
    fee_id              BIGINT REFERENCES tdb.fees (id),           -- nullable
    promotion_id        BIGINT REFERENCES tdb.promotions (id),     -- nullable

    type                VARCHAR(30) NOT NULL,   -- TRADE, DEPOSIT, WITHDRAWAL, FEE, DIVIDEND, PROMOTION_CREDIT
    amount              DECIMAL(18,2) NOT NULL, -- có thể âm cho debit
    currency            VARCHAR(10) NOT NULL DEFAULT 'VND',

    status              VARCHAR(20) NOT NULL DEFAULT 'completed',

    description         TEXT,
    reference_number    VARCHAR(50),

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,

    created_by          BIGINT,

    CONSTRAINT uq_transactions_reference UNIQUE (reference_number),
    CONSTRAINT chk_transactions_type CHECK (
        type IN ('TRADE', 'DEPOSIT', 'WITHDRAWAL', 'FEE', 'DIVIDEND', 'PROMOTION_CREDIT')
    ),
    CONSTRAINT chk_transactions_status CHECK (status IN ('pending', 'completed', 'failed', 'reversed'))
);

-- ---------------------------------------------------------------------
-- Table: tdb.user_stock_portfolio
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tdb.user_stock_portfolio (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id             BIGINT NOT NULL REFERENCES tdb.users (id),
    stock_id            VARCHAR(10) NOT NULL REFERENCES tdb.stocks (id),

    quantity            INT NOT NULL DEFAULT 0,
    avg_cost            DECIMAL(10,2),
    total_cost          DECIMAL(18,2),   -- quantity * avg_cost

    current_price       DECIMAL(10,2),
    current_value       DECIMAL(18,2),   -- quantity * current_price

    realized_pnl        DECIMAL(18,2) NOT NULL DEFAULT 0,
    unrealized_pnl      DECIMAL(18,2),   -- current_value - total_cost
    return_percent      DECIMAL(10,4),   -- (unrealized_pnl / total_cost) * 100

    first_buy_at        TIMESTAMPTZ,
    last_trade_at       TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_user_stock_portfolio UNIQUE (user_id, stock_id)
);

-- =====================================================================
-- Triggers: tự động set updated_at cho mọi bảng có cột này
-- (user_stock_interests không có updated_at nên không cần trigger)
-- =====================================================================
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'companies', 'stocks', 'banks', 'addresses', 'fees', 'promotions',
        'users', 'wallets', 'user_bank_linked', 'user_fees', 'user_promotions',
        'wallet_transactions', 'orders', 'transactions', 'user_stock_portfolio'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_set_updated_at ON tdb.%1$s', tbl);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_set_updated_at BEFORE UPDATE ON tdb.%1$s FOR EACH ROW EXECUTE FUNCTION tdb.set_updated_at()',
            tbl
        );
    END LOOP;
END
$$;

-- =====================================================================
-- Indexes
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_stocks_company                     ON tdb.stocks (company_id);

CREATE INDEX IF NOT EXISTS idx_users_status                       ON tdb.users (status);
CREATE INDEX IF NOT EXISTS idx_users_address                      ON tdb.users (address_id);

CREATE INDEX IF NOT EXISTS idx_wallets_user                       ON tdb.wallets (user_id);

CREATE INDEX IF NOT EXISTS idx_user_bank_linked_user               ON tdb.user_bank_linked (user_id);
CREATE INDEX IF NOT EXISTS idx_user_bank_linked_bank                ON tdb.user_bank_linked (bank_id);

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_wallet_created  ON tdb.wallet_transactions (wallet_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status          ON tdb.wallet_transactions (status);

CREATE INDEX IF NOT EXISTS idx_orders_user_status                  ON tdb.orders (user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_stock_date                   ON tdb.orders (stock_id, order_date);
CREATE INDEX IF NOT EXISTS idx_orders_created                      ON tdb.orders (created_at);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date              ON tdb.transactions (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_type_status            ON tdb.transactions (type, status);
CREATE INDEX IF NOT EXISTS idx_transactions_order                  ON tdb.transactions (order_id);

CREATE INDEX IF NOT EXISTS idx_user_fees_user                      ON tdb.user_fees (user_id);
CREATE INDEX IF NOT EXISTS idx_user_promotions_user                 ON tdb.user_promotions (user_id);
CREATE INDEX IF NOT EXISTS idx_user_stock_interests_user             ON tdb.user_stock_interests (user_id);

CREATE INDEX IF NOT EXISTS idx_user_stock_portfolio_user_value      ON tdb.user_stock_portfolio (user_id, current_value DESC);

-- =====================================================================
-- CDC via WAL (logical decoding, wal2json plugin -- see simulated_app/Dockerfile)
-- Consumed with a plain SQL connection via pg_logical_slot_peek_changes() /
-- pg_replication_slot_advance() -- no pg_recvlogical, no Debezium/Kafka.
-- Covers every table in the schema (single pub/slot pair).
-- NOTE: pipelines/orchestration/orch__tdb__users.py still hardcodes
-- slot_name="cdc_users_slot" -- update it to "cdc_tdb_slot" separately.
-- Guarded with existence checks so this stays safe to re-run (pg-init is
-- re-run on demand, and CREATE PUBLICATION / pg_create_logical_replication_slot
-- have no IF NOT EXISTS form).
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'cdc_tdb_pub') THEN
        CREATE PUBLICATION cdc_tdb_pub FOR TABLES IN SCHEMA tdb;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'cdc_tdb_slot') THEN
        PERFORM pg_create_logical_replication_slot('cdc_tdb_slot', 'wal2json');
    END IF;
END
$$;

-- NOTE: the slot only captures changes from this point forward, and this
-- script no longer seeds any rows. ingest__tdb.py's first run should still do
-- a full snapshot of each source table as a baseline before relying on the
-- CDC export for incremental changes (relevant again once mock data is added
-- elsewhere).
