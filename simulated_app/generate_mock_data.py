"""Fill the `tdb` schema (see generate_script.sql / ERD_DESIGN_README.md) with
small, internally-consistent fake data.

Standalone by design: no imports from `pipelines/`, no env vars, no CLI args.
Connection settings and generation volume are hardcoded constants below --
edit them directly if you need something different.

Run against a freshly-initialized schema:
    docker compose run --rm pg-init
    python simulated_app/generate_mock_data.py

NOTE on re-running: RANDOM_SEED is fixed, so every run produces the exact same
names/emails/tickers. Re-running against a DB that already has data from a
previous run WILL fail on unique constraints (users.email, banks.name, ...) --
that's intentional (fail obviously rather than silently duplicate). Re-run
`pg-init` for a clean schema before generating again, or DROP SCHEMA tdb
CASCADE yourself first.

Requires: faker, psycopg2-binary (see requirements.txt).
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

NUM_COMPANIES = 20
STOCKS_PER_COMPANY_RANGE = (1, 3)
NUM_BANKS = 8
NUM_USERS = 50
BANK_LINKS_PER_USER_RANGE = (0, 2)
WATCHLIST_PER_USER_RANGE = (0, 5)
PROMO_GRANT_RATE = 0.3
DEPOSITS_PER_USER_RANGE = (1, 5)
DEPOSIT_AMOUNT_RANGE_VND = (2_000_000, 50_000_000)
ORDERS_PER_FUNDED_USER_RANGE = (1, 8)
ORDER_FILL_RATE = 0.75
TRADING_FEE_PCT = Decimal("0.0015")  # 0.15%
LOT_SIZE = 100

VN_BANKS = [
    ("Vietcombank", "VCB"), ("Techcombank", "TCB"), ("BIDV", "BIDV"),
    ("VietinBank", "CTG"), ("ACB", "ACB"), ("MB Bank", "MBB"),
    ("VPBank", "VPB"), ("Sacombank", "STB"), ("TPBank", "TPB"),
    ("HDBank", "HDB"),
][:NUM_BANKS]

fake = Faker("vi_VN")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


def _pg_connect():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="simulated_app",
        user="trading",
        password="trading",
    )


def q2(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def insert_rows(cur, table: str, columns: list[str], rows: list[dict], returning: str | None = "id"):
    """Batch-insert `rows` (each a dict keyed by `columns`) into `table`.
    Returns the RETURNING values in insertion order, or [] if returning=None.
    """
    if not rows:
        return []
    values = [tuple(row[c] for c in columns) for row in rows]
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
    if returning:
        query += f" RETURNING {returning}"
        result = execute_values(cur, query, values, fetch=True)
        return [r[0] for r in result]
    execute_values(cur, query, values)
    return []


def random_ticker(existing: set[str]) -> str:
    while True:
        length = random.choice([3, 3, 3, 4])
        code = "".join(random.choices(string.ascii_uppercase, k=length))
        if code not in existing:
            existing.add(code)
            return code


# ---------------------------------------------------------------------------
# 1. companies
# ---------------------------------------------------------------------------
def gen_companies(cur):
    sectors = ["Banking", "Real Estate", "Retail", "Manufacturing", "Energy",
               "Technology", "Food & Beverage", "Logistics", "Healthcare", "Construction"]
    rows = [
        {
            "name": fake.company(),
            "sector": random.choice(sectors),
            "description": fake.catch_phrase(),
            "website": fake.domain_name(),
            "status": random.choices(["active", "inactive", "delisted"], weights=[92, 5, 3])[0],
        }
        for _ in range(NUM_COMPANIES)
    ]
    ids = insert_rows(cur, "tdb.companies", ["name", "sector", "description", "website", "status"], rows)
    for row, row_id in zip(rows, ids):
        row["id"] = row_id
    return rows


# ---------------------------------------------------------------------------
# 2. stocks
# ---------------------------------------------------------------------------
def gen_stocks(cur, companies: list[dict]):
    used_tickers: set[str] = set()
    rows = []
    for company in companies:
        for _ in range(random.randint(*STOCKS_PER_COMPANY_RANGE)):
            base_price = random.uniform(10_000, 200_000)  # VND
            rows.append({
                "id": random_ticker(used_tickers),
                "company_id": company["id"],
                "name": f"{company['name']} Stock",
                "exchange": random.choice(["HOSE", "HNX", "UPCOM"]),
                "market_cap": random.randint(500_000_000_000, 50_000_000_000_000),
                "sector": company["sector"],
                "min_price": q2(base_price * 0.8),
                "max_price": q2(base_price * 1.2),
                "min_lot_size": LOT_SIZE,
                "price_tick": Decimal("100.0000"),
                "status": "active",
            })
    insert_rows(
        cur, "tdb.stocks",
        ["id", "company_id", "name", "exchange", "market_cap", "sector",
         "min_price", "max_price", "min_lot_size", "price_tick", "status"],
        rows, returning=None,
    )
    # Track a live "current price" per ticker, seeded at the row's midpoint.
    prices = {row["id"]: q2((row["min_price"] + row["max_price"]) / 2) for row in rows}
    return rows, prices


# ---------------------------------------------------------------------------
# 3. banks
# ---------------------------------------------------------------------------
def gen_banks(cur):
    rows = [
        {"name": name, "code": code, "country": "Vietnam",
         "api_endpoint": f"https://api.{code.lower()}.example.vn", "is_active": True}
        for name, code in VN_BANKS
    ]
    ids = insert_rows(cur, "tdb.banks", ["name", "code", "country", "api_endpoint", "is_active"], rows)
    for row, row_id in zip(rows, ids):
        row["id"] = row_id
    return rows


# ---------------------------------------------------------------------------
# 4. fees & promotions (shared catalogs)
# ---------------------------------------------------------------------------
def gen_fees(cur):
    rows = [
        {"name": "Trading Commission", "type": "TRADING_COMMISSION", "amount": None,
         "percentage": TRADING_FEE_PCT, "applicable_to": "ALL", "min_amount": None,
         "effective_from": None, "effective_to": None, "status": "active"},
        {"name": "Withdrawal Fee", "type": "WITHDRAWAL", "amount": Decimal("11000"),
         "percentage": None, "applicable_to": "ALL", "min_amount": None,
         "effective_from": None, "effective_to": None, "status": "active"},
        {"name": "Monthly Account Fee", "type": "MONTHLY", "amount": Decimal("0"),
         "percentage": None, "applicable_to": "basic", "min_amount": None,
         "effective_from": None, "effective_to": None, "status": "active"},
    ]
    ids = insert_rows(
        cur, "tdb.fees",
        ["name", "type", "amount", "percentage", "applicable_to", "min_amount",
         "effective_from", "effective_to", "status"],
        rows,
    )
    for row, row_id in zip(rows, ids):
        row["id"] = row_id
    return {row["type"]: row for row in rows}


def gen_promotions(cur):
    rows = [
        {"name": "Welcome Bonus", "description": "Free trade for new users", "type": "FREE_TRADE",
         "discount_percent": None, "discount_amount": None, "max_discount": None,
         "applicable_to": "NEW_USERS", "min_transaction_amount": None, "usage_limit_per_user": 1,
         "valid_from": None, "valid_to": None, "status": "active"},
        {"name": "September Cashback", "description": "10% cashback on trading fees", "type": "CASHBACK",
         "discount_percent": Decimal("10"), "discount_amount": None, "max_discount": Decimal("100000"),
         "applicable_to": "ALL", "min_transaction_amount": None, "usage_limit_per_user": 5,
         "valid_from": None, "valid_to": None, "status": "active"},
    ]
    ids = insert_rows(
        cur, "tdb.promotions",
        ["name", "description", "type", "discount_percent", "discount_amount", "max_discount",
         "applicable_to", "min_transaction_amount", "usage_limit_per_user",
         "valid_from", "valid_to", "status"],
        rows,
    )
    for row, row_id in zip(rows, ids):
        row["id"] = row_id
    return rows


# ---------------------------------------------------------------------------
# 5. per-user onboarding: addresses -> users -> wallets -> close wallet_id FK
# ---------------------------------------------------------------------------
def gen_users_onboarding(cur, now: datetime):
    address_rows = []
    user_created_ats = []
    for _ in range(NUM_USERS):
        street = fake.street_address()
        city = fake.city()
        address_rows.append({
            "street": street,
            "city": city,
            "province": city,  # vi_VN Faker has no distinct province field
            "country": "Vietnam",
            "postal_code": fake.postcode(),
        })
        user_created_ats.append(now - timedelta(days=random.uniform(1, 90)))
    address_ids = insert_rows(cur, "tdb.addresses", ["street", "city", "province", "country", "postal_code"], address_rows)

    user_rows = []
    for address_id, created_at in zip(address_ids, user_created_ats):
        name = fake.name()
        user_rows.append({
            "email": fake.unique.email(),
            "name": name,
            "phone": fake.phone_number()[:20],
            "kyc_level": random.choices([0, 1, 2], weights=[10, 30, 60])[0],
            "identity_number": "".join(random.choices(string.digits, k=12)),
            "address_id": address_id,
            "status": random.choices(["active", "suspended", "banned", "closed"], weights=[90, 4, 3, 3])[0],
            "user_type": random.choices(["individual", "institutional"], weights=[95, 5])[0],
            "risk_profile": random.choices(
                [None, "conservative", "moderate", "aggressive"], weights=[10, 30, 40, 20]
            )[0],
            "daily_loss_limit": q2(random.uniform(5_000_000, 100_000_000)),
            "created_at": created_at,
        })
    user_ids = insert_rows(
        cur, "tdb.users",
        ["email", "name", "phone", "kyc_level", "identity_number", "address_id",
         "status", "user_type", "risk_profile", "daily_loss_limit", "created_at"],
        user_rows,
    )
    for row, row_id in zip(user_rows, user_ids):
        row["id"] = row_id

    wallet_rows = [{"user_id": row["id"], "created_at": row["created_at"]} for row in user_rows]
    wallet_ids = insert_rows(cur, "tdb.wallets", ["user_id", "created_at"], wallet_rows)
    for row, row_id in zip(wallet_rows, wallet_ids):
        row["id"] = row_id

    # Close the circular users.wallet_id -> wallets.id reference.
    cur.executemany(
        "UPDATE tdb.users SET wallet_id = %s WHERE id = %s",
        [(w["id"], w["user_id"]) for w in wallet_rows],
    )

    wallets_by_user = {w["user_id"]: w for w in wallet_rows}
    return user_rows, wallets_by_user


# ---------------------------------------------------------------------------
# 6. user_bank_linked
# ---------------------------------------------------------------------------
def gen_user_bank_linked(cur, users: list[dict], banks: list[dict]):
    rows = []
    links_by_user: dict[int, list[dict]] = {}
    for user in users:
        for bank in random.sample(banks, k=min(len(banks), random.randint(*BANK_LINKS_PER_USER_RANGE))):
            linked_at = user["created_at"] + timedelta(hours=random.uniform(1, 48))
            row = {
                "user_id": user["id"],
                "bank_id": bank["id"],
                "account_number": "".join(random.choices(string.digits, k=12)),
                "account_holder_name": user["name"].upper(),
                "account_type": random.choice(["checking", "savings"]),
                "status": "active",
                "is_verified": random.random() < 0.9,
                "linked_at": linked_at,
                "created_at": linked_at,
            }
            rows.append(row)
    ids = insert_rows(
        cur, "tdb.user_bank_linked",
        ["user_id", "bank_id", "account_number", "account_holder_name", "account_type",
         "status", "is_verified", "linked_at", "created_at"],
        rows,
    )
    for row, row_id in zip(rows, ids):
        row["id"] = row_id
        links_by_user.setdefault(row["user_id"], []).append(row)
    return links_by_user


# ---------------------------------------------------------------------------
# 7. user_fees / user_promotions
# ---------------------------------------------------------------------------
def gen_user_fees(cur, users: list[dict], fees_by_type: dict):
    trading_fee = fees_by_type["TRADING_COMMISSION"]
    rows = [
        {"user_id": user["id"], "fee_id": trading_fee["id"],
         "applied_from": user["created_at"].date(), "applied_to": None, "status": "active"}
        for user in users
    ]
    insert_rows(cur, "tdb.user_fees", ["user_id", "fee_id", "applied_from", "applied_to", "status"], rows, returning=None)
    return {user["id"]: trading_fee for user in users}


def gen_user_promotions(cur, users: list[dict], promotions: list[dict]):
    welcome = next(p for p in promotions if p["type"] == "FREE_TRADE")
    rows = []
    for user in users:
        if random.random() < PROMO_GRANT_RATE:
            rows.append({
                "user_id": user["id"],
                "promotion_id": welcome["id"],
                "claimed_at": user["created_at"] + timedelta(hours=1),
                "used_count": 0,
                "expires_at": user["created_at"] + timedelta(days=180),
                "status": "active",
            })
    insert_rows(
        cur, "tdb.user_promotions",
        ["user_id", "promotion_id", "claimed_at", "used_count", "expires_at", "status"],
        rows, returning=None,
    )


# ---------------------------------------------------------------------------
# 8. user_stock_interests (watchlist)
# ---------------------------------------------------------------------------
def gen_user_stock_interests(cur, users: list[dict], stocks: list[dict]):
    rows = []
    for user in users:
        k = min(len(stocks), random.randint(*WATCHLIST_PER_USER_RANGE))
        for stock in random.sample(stocks, k=k):
            added_at = user["created_at"] + timedelta(hours=random.uniform(1, 72))
            rows.append({
                "user_id": user["id"],
                "stock_id": stock["id"],
                "added_at": added_at,
                "last_viewed_at": added_at + timedelta(hours=random.uniform(0, 24)),
                "view_count": random.randint(1, 20),
                "status": "active",
            })
    insert_rows(
        cur, "tdb.user_stock_interests",
        ["user_id", "stock_id", "added_at", "last_viewed_at", "view_count", "status"],
        rows, returning=None,
    )


# ---------------------------------------------------------------------------
# 9. wallet funding (deposits) -- feeds the in-memory wallet balances
# ---------------------------------------------------------------------------
def gen_deposits(cur, users: list[dict], wallets_by_user: dict, links_by_user: dict):
    balances: dict[int, Decimal] = {user["id"]: Decimal("0") for user in users}
    rows = []
    for user in users:
        links = links_by_user.get(user["id"])
        if not links:
            continue  # no linked bank -> can't deposit
        wallet = wallets_by_user[user["id"]]
        when = wallet["created_at"] + timedelta(hours=random.uniform(1, 24))
        for _ in range(random.randint(*DEPOSITS_PER_USER_RANGE)):
            amount = q2(random.uniform(*DEPOSIT_AMOUNT_RANGE_VND))
            when = when + timedelta(hours=random.uniform(1, 72))
            link = random.choice(links)
            rows.append({
                "wallet_id": wallet["id"],
                "user_bank_linked_id": link["id"],
                "type": "DEPOSIT",
                "amount": amount,
                "currency": "VND",
                "status": "completed",
                "reference_number": f"DEP-{user['id']}-{len(rows)+1:06d}",
                "description": "Wallet top-up",
                "created_at": when,
                "completed_at": when,
            })
            balances[user["id"]] += amount
    insert_rows(
        cur, "tdb.wallet_transactions",
        ["wallet_id", "user_bank_linked_id", "type", "amount", "currency", "status",
         "reference_number", "description", "created_at", "completed_at"],
        rows, returning=None,
    )
    return balances


# ---------------------------------------------------------------------------
# 10. orders -> transactions -> portfolio (the core trading flow)
# ---------------------------------------------------------------------------
def gen_orders_and_trades(cur, users, wallets_by_user, stocks, prices, fees_by_user, balances):
    order_rows = []
    txn_rows = []
    portfolio = {}  # (user_id, stock_id) -> holding dict

    funded_users = [u for u in users if balances[u["id"]] > 0]
    for user in funded_users:
        wallet = wallets_by_user[user["id"]]
        fee = fees_by_user[user["id"]]
        when = wallet["created_at"] + timedelta(days=random.uniform(1, 30))

        for _ in range(random.randint(*ORDERS_PER_FUNDED_USER_RANGE)):
            when = when + timedelta(hours=random.uniform(2, 48))
            held_stocks = [sid for (uid, sid), h in portfolio.items() if uid == user["id"] and h["quantity"] > 0]

            if held_stocks and random.random() < 0.4:
                side = "SELL"
                stock_id = random.choice(held_stocks)
            else:
                side = "BUY"
                stock_id = random.choice(stocks)["id"]

            price = q2(prices[stock_id] * Decimal(str(random.uniform(0.98, 1.02))))
            quantity = random.choice([100, 200, 300, 500, 1000])

            if side == "SELL":
                held_qty = portfolio[(user["id"], stock_id)]["quantity"]
                quantity = min(quantity, held_qty)
                if quantity < LOT_SIZE:
                    continue
                gross = price * quantity
                fee_amount = q2(gross * TRADING_FEE_PCT)
                net_cash = gross - fee_amount
            else:
                gross = price * quantity
                fee_amount = q2(gross * TRADING_FEE_PCT)
                total_cost = gross + fee_amount
                if balances[user["id"]] < total_cost:
                    affordable_qty = int(balances[user["id"]] / (price * (1 + TRADING_FEE_PCT)) // LOT_SIZE) * LOT_SIZE
                    if affordable_qty < LOT_SIZE:
                        order_rows.append({
                            "user_id": user["id"], "stock_id": stock_id, "side": side,
                            "quantity": quantity, "price": price, "order_type": "LIMIT",
                            "filled_quantity": 0, "filled_price": None, "average_filled_price": None,
                            "status": "rejected", "order_date": when.date(), "order_time": when.time(),
                            "created_at": when, "filled_at": None, "cancelled_at": None,
                        })
                        continue
                    quantity = affordable_qty
                gross = price * quantity
                fee_amount = q2(gross * TRADING_FEE_PCT)
                net_cash = -(gross + fee_amount)

            will_fill = random.random() < ORDER_FILL_RATE
            if not will_fill:
                order_rows.append({
                    "user_id": user["id"], "stock_id": stock_id, "side": side,
                    "quantity": quantity, "price": price, "order_type": "LIMIT",
                    "filled_quantity": 0, "filled_price": None, "average_filled_price": None,
                    "status": random.choice(["pending", "cancelled"]),
                    "order_date": when.date(), "order_time": when.time(),
                    "created_at": when, "filled_at": None,
                    "cancelled_at": when if random.random() < 0.5 else None,
                })
                continue

            filled_at = when + timedelta(minutes=random.uniform(1, 30))
            order_rows.append({
                "user_id": user["id"], "stock_id": stock_id, "side": side,
                "quantity": quantity, "price": price, "order_type": "LIMIT",
                "filled_quantity": quantity, "filled_price": price, "average_filled_price": price,
                "status": "filled", "order_date": when.date(), "order_time": when.time(),
                "created_at": when, "filled_at": filled_at, "cancelled_at": None,
            })
            # order_rows[-1] gets an "id" placeholder wired in after insert (see below)
            order_rows[-1]["_txn_after_insert"] = {
                "user_id": user["id"], "wallet_id": wallet["id"], "fee_id": fee["id"],
                "side": side, "quantity": quantity, "price": price,
                "net_cash": net_cash, "fee_amount": fee_amount, "when": filled_at,
            }

            balances[user["id"]] += net_cash
            prices[stock_id] = price  # market drifts to the executed price

            holding = portfolio.setdefault((user["id"], stock_id), {
                "quantity": 0, "total_cost": Decimal("0"), "realized_pnl": Decimal("0"),
                "first_buy_at": filled_at, "last_trade_at": filled_at,
            })
            if side == "BUY":
                holding["total_cost"] += gross + fee_amount
                holding["quantity"] += quantity
            else:
                avg_cost = holding["total_cost"] / holding["quantity"] if holding["quantity"] else Decimal("0")
                holding["realized_pnl"] += (price - avg_cost) * quantity - fee_amount
                holding["total_cost"] -= avg_cost * quantity
                holding["quantity"] -= quantity
            holding["last_trade_at"] = filled_at

    # Insert orders, then build transactions referencing the returned order ids.
    columns = ["user_id", "stock_id", "side", "quantity", "price", "order_type",
               "filled_quantity", "filled_price", "average_filled_price", "status",
               "order_date", "order_time", "created_at", "filled_at", "cancelled_at"]
    pending_txn_specs = [row.pop("_txn_after_insert", None) for row in order_rows]
    order_ids = insert_rows(cur, "tdb.orders", columns, order_rows)

    for order_id, spec in zip(order_ids, pending_txn_specs):
        if spec is None:
            continue
        gross = spec["price"] * spec["quantity"]
        txn_rows.append({
            "user_id": spec["user_id"], "wallet_id": spec["wallet_id"], "order_id": order_id,
            "fee_id": spec["fee_id"], "promotion_id": None,
            "type": "TRADE", "amount": spec["net_cash"], "currency": "VND",
            "status": "completed", "description": f"{spec['side']} {spec['quantity']} @ {spec['price']}",
            "reference_number": f"TXN-{order_id}",
            "created_at": spec["when"], "completed_at": spec["when"],
        })
    insert_rows(
        cur, "tdb.transactions",
        ["user_id", "wallet_id", "order_id", "fee_id", "promotion_id", "type", "amount",
         "currency", "status", "description", "reference_number", "created_at", "completed_at"],
        txn_rows, returning=None,
    )
    return portfolio


# ---------------------------------------------------------------------------
# 11. flush wallet balances & portfolio holdings computed above
# ---------------------------------------------------------------------------
def flush_wallets(cur, wallets_by_user: dict, balances: dict):
    cur.executemany(
        "UPDATE tdb.wallets SET balance = %s WHERE id = %s",
        [(balances[uid], w["id"]) for uid, w in wallets_by_user.items()],
    )


def flush_portfolio(cur, portfolio: dict, prices: dict):
    rows = []
    for (user_id, stock_id), h in portfolio.items():
        if h["quantity"] <= 0:
            continue
        current_price = prices[stock_id]
        current_value = q2(current_price * h["quantity"])
        total_cost = q2(h["total_cost"])
        avg_cost = q2(total_cost / h["quantity"])
        unrealized_pnl = q2(current_value - total_cost)
        return_percent = (unrealized_pnl / total_cost * 100) if total_cost > 0 else None
        rows.append({
            "user_id": user_id, "stock_id": stock_id, "quantity": h["quantity"],
            "avg_cost": avg_cost, "total_cost": total_cost,
            "current_price": current_price, "current_value": current_value,
            "realized_pnl": q2(h["realized_pnl"]), "unrealized_pnl": unrealized_pnl,
            "return_percent": return_percent.quantize(Decimal("0.0001")) if return_percent is not None else None,
            "first_buy_at": h["first_buy_at"], "last_trade_at": h["last_trade_at"],
        })
    insert_rows(
        cur, "tdb.user_stock_portfolio",
        ["user_id", "stock_id", "quantity", "avg_cost", "total_cost", "current_price",
         "current_value", "realized_pnl", "unrealized_pnl", "return_percent",
         "first_buy_at", "last_trade_at"],
        rows, returning=None,
    )
    return len(rows)


def main():
    now = datetime.now()
    conn = _pg_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                companies = gen_companies(cur)
                stocks, prices = gen_stocks(cur, companies)
                banks = gen_banks(cur)
                fees_by_type = gen_fees(cur)
                promotions = gen_promotions(cur)
                users, wallets_by_user = gen_users_onboarding(cur, now)
                links_by_user = gen_user_bank_linked(cur, users, banks)
                fees_by_user = gen_user_fees(cur, users, fees_by_type)
                gen_user_promotions(cur, users, promotions)
                gen_user_stock_interests(cur, users, stocks)
                balances = gen_deposits(cur, users, wallets_by_user, links_by_user)
                portfolio = gen_orders_and_trades(cur, users, wallets_by_user, stocks, prices, fees_by_user, balances)
                flush_wallets(cur, wallets_by_user, balances)
                n_holdings = flush_portfolio(cur, portfolio, prices)

                print(f"companies            {len(companies)}")
                print(f"stocks               {len(stocks)}")
                print(f"banks                {len(banks)}")
                print(f"fees                 {len(fees_by_type)}")
                print(f"promotions           {len(promotions)}")
                print(f"users                {len(users)}")
                print(f"wallets              {len(wallets_by_user)}")
                print(f"user_bank_linked     {sum(len(v) for v in links_by_user.values())}")
                print(f"funded users         {sum(1 for b in balances.values() if b != 0)}")
                print(f"portfolio holdings   {n_holdings}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
