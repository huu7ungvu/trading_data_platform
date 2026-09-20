# ✅ ER Design Review & Field Recommendations

## **Verdict: 🟢 EXCELLENT - Production Ready**

```
✅ Relationship structure perfect
✅ Bridge tables correctly implemented
✅ All necessary tables included
✅ Ready for field definition
```

---

## **Field Recommendations (Per Table)**

### **1. COMPANIES** (Reference Data)

```sql
CREATE TABLE companies (
  -- PKs & FKs
  id INT PRIMARY KEY,
  
  -- Business fields
  name VARCHAR(255) NOT NULL,
  sector VARCHAR(100),
  description TEXT,
  website VARCHAR(255),
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, inactive, delisted
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **2. STOCKS** (Reference Data)

```sql
CREATE TABLE stocks (
  id VARCHAR(10) PRIMARY KEY,  -- VNM, ACB, etc
  company_id INT NOT NULL FOREIGN KEY,
  
  -- Stock details
  name VARCHAR(255) NOT NULL,
  exchange VARCHAR(20),  -- HOSE, HNX, UPCOM
  market_cap BIGINT,
  sector VARCHAR(100),
  
  -- Trading specs
  min_price DECIMAL(10,2),
  max_price DECIMAL(10,2),
  min_lot_size INT DEFAULT 1,
  price_tick DECIMAL(10,4) DEFAULT 0.01,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, suspended, delisted
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **3. BANKS** (Reference Data)

```sql
CREATE TABLE banks (
  id INT PRIMARY KEY,
  
  -- Bank info
  name VARCHAR(100) NOT NULL UNIQUE,
  code VARCHAR(20),
  country VARCHAR(50),
  
  -- Integration
  api_endpoint VARCHAR(255),
  is_active BOOLEAN DEFAULT true,
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **4. ADDRESSES** (Reference/Dimension)

```sql
CREATE TABLE addresses (
  id INT PRIMARY KEY,
  
  -- Address fields
  street VARCHAR(255),
  city VARCHAR(100),
  province VARCHAR(100),
  country VARCHAR(100),
  postal_code VARCHAR(20),
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **5. USERS** (Core Entity) ⭐

```sql
CREATE TABLE users (
  id INT PRIMARY KEY,
  
  -- Identity
  email VARCHAR(255) NOT NULL UNIQUE,
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(20),
  
  -- KYC
  kyc_level INT DEFAULT 0,  -- 0=not verified, 1=basic, 2=full
  identity_number VARCHAR(50) UNIQUE,
  
  -- Foreign Keys
  address_id INT FOREIGN KEY,
  wallet_id INT FOREIGN KEY,
  
  -- Status & Type
  status VARCHAR(20) DEFAULT 'active',  -- active, suspended, banned, closed
  user_type VARCHAR(20) DEFAULT 'individual',  -- individual, institutional
  
  -- Risk profile
  risk_profile VARCHAR(20),  -- conservative, moderate, aggressive
  daily_loss_limit DECIMAL(15,2),
  
  -- Account info
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  last_login_at TIMESTAMP,
  
  -- Audit
  created_by INT,
  updated_by INT
);
```

---

### **6. WALLETS** (Core Entity) ⭐

```sql
CREATE TABLE wallets (
  id INT PRIMARY KEY,
  
  -- Ownership (implicit user_id via users.wallet_id, but good to explicit)
  user_id INT NOT NULL FOREIGN KEY,
  
  -- Balance
  balance DECIMAL(18,2) NOT NULL DEFAULT 0,
  currency VARCHAR(10) DEFAULT 'VND',
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, frozen, closed
  
  -- Limits
  daily_withdrawal_limit DECIMAL(15,2),
  total_withdrawn_today DECIMAL(15,2) DEFAULT 0,
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **7. USER_BANK_LINKED** (Bridge)

```sql
CREATE TABLE user_bank_linked (
  id INT PRIMARY KEY,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  bank_id INT NOT NULL FOREIGN KEY,
  
  -- Bank account details
  account_number VARCHAR(50) NOT NULL,
  account_holder_name VARCHAR(255),
  account_type VARCHAR(20),  -- checking, savings
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, inactive, unverified, deleted
  is_verified BOOLEAN DEFAULT false,
  
  -- Metadata
  linked_at TIMESTAMP DEFAULT NOW(),
  verified_at TIMESTAMP,
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(user_id, bank_id, account_number)
);
```

---

### **8. WALLET_TRANSACTIONS** (Fact Table)

```sql
CREATE TABLE wallet_transactions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  
  -- Foreign Keys
  wallet_id INT NOT NULL FOREIGN KEY,
  user_bank_linked_id INT FOREIGN KEY,  -- nullable (internal transfer)
  
  -- Transaction details
  type VARCHAR(20) NOT NULL,  -- DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT, FEE
  amount DECIMAL(18,2) NOT NULL,
  currency VARCHAR(10) DEFAULT 'VND',
  
  -- Status
  status VARCHAR(20) DEFAULT 'pending',  -- pending, completed, failed, reversed
  
  -- Metadata
  reference_number VARCHAR(50) UNIQUE,
  description TEXT,
  
  -- Timestamp
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  
  -- Audit
  created_by INT,
  
  INDEX idx_wallet_created (wallet_id, created_at),
  INDEX idx_status (status)
);
```

---

### **9. ORDERS** (Fact Table - CRITICAL) ⭐

```sql
CREATE TABLE orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  stock_id VARCHAR(10) NOT NULL FOREIGN KEY,
  
  -- Order details
  side VARCHAR(10) NOT NULL,  -- BUY, SELL
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  order_type VARCHAR(20) DEFAULT 'LIMIT',  -- LIMIT, MARKET, STOP
  
  -- Execution
  filled_quantity INT DEFAULT 0,
  filled_price DECIMAL(10,2),
  average_filled_price DECIMAL(10,2),
  
  -- Status
  status VARCHAR(20) DEFAULT 'pending',  -- pending, partially_filled, filled, cancelled, rejected, expired
  
  -- Metadata
  order_date DATE,
  order_time TIME,
  
  -- Timestamp
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  filled_at TIMESTAMP,
  cancelled_at TIMESTAMP,
  
  -- Audit
  created_by INT,
  cancelled_by INT,
  cancellation_reason VARCHAR(255),
  
  INDEX idx_user_status (user_id, status),
  INDEX idx_stock_date (stock_id, order_date),
  INDEX idx_created (created_at)
);
```

---

### **10. TRANSACTIONS** (Fact Table - ALL ACTIVITIES) ⭐

```sql
CREATE TABLE transactions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  wallet_id INT FOREIGN KEY,  -- nullable (some txns may not touch wallet)
  order_id INT FOREIGN KEY,  -- nullable (non-trading txns)
  fee_id INT FOREIGN KEY,  -- nullable
  promotion_id INT FOREIGN KEY,  -- nullable
  
  -- Transaction details
  type VARCHAR(30) NOT NULL,  -- TRADE, DEPOSIT, WITHDRAWAL, FEE, DIVIDEND, PROMOTION_CREDIT
  amount DECIMAL(18,2) NOT NULL,  -- can be negative for debits
  currency VARCHAR(10) DEFAULT 'VND',
  
  -- Status
  status VARCHAR(20) DEFAULT 'completed',  -- pending, completed, failed, reversed
  
  -- Metadata
  description TEXT,
  reference_number VARCHAR(50) UNIQUE,
  
  -- Timestamp
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  
  -- Audit
  created_by INT,
  
  INDEX idx_user_date (user_id, created_at),
  INDEX idx_type_status (type, status),
  INDEX idx_order_id (order_id)
);
```

---

### **11. FEES** (Reference Data)

```sql
CREATE TABLE fees (
  id INT PRIMARY KEY,
  
  -- Fee definition
  name VARCHAR(100) NOT NULL,
  type VARCHAR(30) NOT NULL,  -- TRADING_COMMISSION, WITHDRAWAL, DEPOSIT, MONTHLY
  amount DECIMAL(10,4),  -- Fixed amount
  percentage DECIMAL(5,4),  -- Percentage (if %)
  
  -- Applicability
  applicable_to VARCHAR(50),  -- ALL, INDIVIDUAL, INSTITUTIONAL, specific_symbol
  min_amount DECIMAL(15,2),  -- minimum transaction amount
  
  -- Timing
  effective_from DATE,
  effective_to DATE,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, inactive, archived
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **12. USER_FEES** (Bridge)

```sql
CREATE TABLE user_fees (
  id INT PRIMARY KEY,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  fee_id INT NOT NULL FOREIGN KEY,
  
  -- Timing (when fee applies to user)
  applied_from DATE NOT NULL,
  applied_to DATE,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, inactive, waived
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(user_id, fee_id, applied_from)
);
```

---

### **13. PROMOTIONS** (Reference Data)

```sql
CREATE TABLE promotions (
  id INT PRIMARY KEY,
  
  -- Promotion details
  name VARCHAR(255) NOT NULL,
  description TEXT,
  type VARCHAR(30),  -- DISCOUNT, CASHBACK, BONUS, FREE_TRADE
  
  -- Value
  discount_percent DECIMAL(5,2),  -- percentage
  discount_amount DECIMAL(15,2),  -- fixed amount
  max_discount DECIMAL(15,2),  -- max discount per use
  
  -- Applicability
  applicable_to VARCHAR(50),  -- ALL, NEW_USERS, specific_symbols
  min_transaction_amount DECIMAL(15,2),
  usage_limit_per_user INT,  -- how many times per user
  
  -- Timing
  valid_from TIMESTAMP,
  valid_to TIMESTAMP,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, inactive, expired, archived
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **14. USER_PROMOTIONS** (Bridge)

```sql
CREATE TABLE user_promotions (
  id INT PRIMARY KEY,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  promotion_id INT NOT NULL FOREIGN KEY,
  
  -- Usage tracking
  claimed_at TIMESTAMP DEFAULT NOW(),
  used_count INT DEFAULT 0,
  expires_at TIMESTAMP,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, used, expired, revoked
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **15. USER_STOCK_INTERESTS** (Bridge)

```sql
CREATE TABLE user_stock_interests (
  id INT PRIMARY KEY,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  stock_id VARCHAR(10) NOT NULL FOREIGN KEY,
  
  -- Tracking
  added_at TIMESTAMP DEFAULT NOW(),
  last_viewed_at TIMESTAMP,
  view_count INT DEFAULT 0,
  
  -- Status
  status VARCHAR(20) DEFAULT 'active',  -- active, removed
  
  UNIQUE(user_id, stock_id)
);
```

---

### **16. USER_STOCK_PORTFOLIO** (Fact Table) ⭐

```sql
CREATE TABLE user_stock_portfolio (
  id INT PRIMARY KEY,
  
  -- Foreign Keys
  user_id INT NOT NULL FOREIGN KEY,
  stock_id VARCHAR(10) NOT NULL FOREIGN KEY,
  
  -- Holdings
  quantity INT NOT NULL DEFAULT 0,
  avg_cost DECIMAL(10,2),
  total_cost DECIMAL(18,2),  -- quantity * avg_cost
  
  -- Current value
  current_price DECIMAL(10,2),
  current_value DECIMAL(18,2),  -- quantity * current_price
  
  -- P&L
  realized_pnl DECIMAL(18,2) DEFAULT 0,
  unrealized_pnl DECIMAL(18,2),  -- current_value - total_cost
  return_percent DECIMAL(10,4),  -- (unrealized_pnl / total_cost) * 100
  
  -- Tracking
  first_buy_at TIMESTAMP,
  last_trade_at TIMESTAMP,
  
  -- Audit
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(user_id, stock_id),
  INDEX idx_user_value (user_id, current_value DESC)
);
```

---

## **Summary Table (All Fields)**

| Table | Record Count | Key Fields | Update Freq | Priority |
|-------|--------------|-----------|-------------|----------|
| companies | ~100 | name, sector | Rarely | Low |
| stocks | ~3000 | id, name, exchange | Daily | High |
| banks | ~50 | name, code | Rarely | Low |
| addresses | ~1M+ | street, city, country | Rarely | Low |
| users | ~100K | email, kyc_level, status | Often | High |
| wallets | ~100K | balance, status | Often | High |
| user_bank_linked | ~100K | account_number, status | Rarely | High |
| wallet_transactions | ~10M+ | type, amount, status | Real-time | Critical |
| orders | ~50M+ | side, quantity, status | Real-time | Critical |
| transactions | ~100M+ | type, amount, status | Real-time | Critical |
| fees | ~50 | type, amount, percentage | Rarely | Low |
| user_fees | ~100K | applied_from, status | Rarely | Low |
| promotions | ~200 | name, discount, valid_to | Often | Low |
| user_promotions | ~500K | claimed_at, used_count | Often | Medium |
| user_stock_interests | ~1M | added_at, last_viewed | Often | Low |
| user_stock_portfolio | ~10M | quantity, avg_cost, unrealized_pnl | Often | Critical |

---

## **Indexing Strategy**

```sql
-- Critical (for query performance)
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_wallets_user ON wallets(user_id);
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
CREATE INDEX idx_orders_stock_date ON orders(stock_id, order_date);
CREATE INDEX idx_transactions_user_date ON transactions(user_id, created_at);
CREATE INDEX idx_portfolio_user_value ON user_stock_portfolio(user_id, current_value DESC);
```

---

## **Next Steps**

```
✅ 1. Finalize all fields (above template)
✅ 2. Add indexes (on frequently queried columns)
✅ 3. Create DDL scripts
✅ 4. Setup CDC triggers (for audit columns)
✅ 5. Seed reference data (companies, stocks, banks, fees)
✅ 6. Start data simulation
```

**Ready to generate SQL CREATE statements?** 🚀