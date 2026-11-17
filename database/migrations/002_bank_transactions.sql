-- 银行流水：只作核对来源。回写汇款表必须人工确认。

CREATE TABLE bank_import_batches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    relative_path text NOT NULL,
    file_name text NOT NULL,
    account_mask text,
    account_name text,
    date_from date,
    date_to date,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bank_import_batches_path_unique UNIQUE (relative_path)
);

CREATE TABLE bank_transactions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES bank_import_batches (id) ON DELETE CASCADE,
    external_uid text NOT NULL,
    txn_date date NOT NULL,
    txn_time time,
    amount numeric(14, 2) NOT NULL,
    direction text NOT NULL,
    balance_after numeric(14, 2),
    counterparty_name text,
    counterparty_account text,
    bank_name text,
    channel text,
    txn_type text,
    purpose text,
    memo text,
    store_id bigint REFERENCES stores (id),
    matched_date date,
    match_status text NOT NULL DEFAULT 'unmatched',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bank_transactions_direction_check CHECK (direction IN ('in', 'out')),
    CONSTRAINT bank_transactions_match_status_check CHECK (
        match_status IN ('unmatched', 'suggested', 'confirmed', 'ignored')
    ),
    CONSTRAINT bank_transactions_uid_unique UNIQUE (external_uid)
);

COMMENT ON COLUMN bank_transactions.external_uid IS '去重键。银行文件无流水号时，由日期时间金额对方账号等拼出。';
COMMENT ON COLUMN bank_transactions.direction IS 'in=收入进账，out=支出。支出不进门店汇款匹配。';
COMMENT ON COLUMN bank_transactions.match_status IS 'unmatched未匹配；suggested系统建议；confirmed人已确认；ignored忽略。';

CREATE INDEX bank_transactions_date_idx ON bank_transactions (txn_date);
CREATE INDEX bank_transactions_store_idx ON bank_transactions (store_id);
CREATE INDEX bank_transactions_status_idx ON bank_transactions (match_status, direction);
