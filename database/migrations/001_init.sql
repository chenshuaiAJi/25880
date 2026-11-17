-- 门店对账：导入后的账以本库为准，不回写 Excel。
-- 余额口径：上月余额 + 本月汇款总额 - 本月发货总额。

CREATE TABLE stores (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name text NOT NULL,
    code text,
    manager_name text,
    phone text,
    address text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT stores_display_name_not_blank CHECK (btrim(display_name) <> '')
);

COMMENT ON TABLE stores IS '门店档案。显示名可改；导入时先按原始名称各建一条，不自动合并。';
COMMENT ON COLUMN stores.display_name IS '列表和单据上展示的当前名称';

CREATE TABLE store_aliases (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id bigint NOT NULL REFERENCES stores (id) ON DELETE CASCADE,
    raw_name text NOT NULL,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT store_aliases_source_check CHECK (source IN ('shipment', 'remittance')),
    CONSTRAINT store_aliases_raw_name_not_blank CHECK (btrim(raw_name) <> ''),
    CONSTRAINT store_aliases_raw_source_unique UNIQUE (raw_name, source)
);

COMMENT ON TABLE store_aliases IS 'Excel 原始名称，不可改。同一原始名称加来源只对应一家店。';
COMMENT ON COLUMN store_aliases.source IS 'shipment=发货单客户名称，remittance=汇款表门店名称';

CREATE TABLE source_files (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL,
    relative_path text NOT NULL,
    file_name text NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL,
    batch_no integer NOT NULL DEFAULT 0,
    batch_label text NOT NULL DEFAULT '',
    biz_date date,
    sheet_name text,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_files_kind_check CHECK (kind IN ('shipment', 'remittance')),
    CONSTRAINT source_files_month_check CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT source_files_batch_check CHECK (batch_no >= 0),
    CONSTRAINT source_files_path_unique UNIQUE (relative_path)
);

COMMENT ON COLUMN source_files.batch_no IS '括号批次用括号里的数字；无括号为 0；字母批次从 101 起，A=101，B=102。';
COMMENT ON COLUMN source_files.batch_label IS '展示用批次。无括号为空，括号批次为 (1)，字母批次为 B。';
COMMENT ON COLUMN source_files.biz_date IS '发货业务日：月份目录 + 文件名起始日。汇款文件为空。';

CREATE INDEX source_files_month_idx ON source_files (kind, year, month);

CREATE TABLE date_conflicts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES source_files (id) ON DELETE CASCADE,
    cell_text text NOT NULL,
    parsed_cell_date date,
    biz_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE date_conflicts IS '单元格发货日期与业务日不一致。业务日仍以文件名为准，这里只列出冲突。';

CREATE INDEX date_conflicts_file_idx ON date_conflicts (source_file_id);

CREATE TABLE import_warnings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id bigint REFERENCES source_files (id) ON DELETE CASCADE,
    code text NOT NULL,
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE remittance_sheets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id bigint UNIQUE REFERENCES source_files (id) ON DELETE CASCADE,
    year integer NOT NULL,
    month integer NOT NULL,
    day_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT remittance_sheets_month_check CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT remittance_sheets_day_count_check CHECK (day_count BETWEEN 1 AND 31),
    CONSTRAINT remittance_sheets_year_month_unique UNIQUE (year, month)
);

COMMENT ON COLUMN remittance_sheets.day_count IS '表上的日期列数。Excel 模板固定铺到 31 日，短月多出来的列也保留，总额才和原表一致。';
COMMENT ON COLUMN remittance_sheets.source_file_id IS '手工创建的下月表可以为空；导入的月表指向源文件。';

CREATE TABLE remittance_rows (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sheet_id bigint NOT NULL REFERENCES remittance_sheets (id) ON DELETE CASCADE,
    store_id bigint NOT NULL REFERENCES stores (id),
    row_index integer NOT NULL,
    imported_raw_name text NOT NULL,
    opening_balance numeric(14, 2) NOT NULL DEFAULT 0,
    CONSTRAINT remittance_rows_sheet_row_unique UNIQUE (sheet_id, row_index)
);

COMMENT ON COLUMN remittance_rows.opening_balance IS '上月余额。下月期初应等于本月期末余额。';
COMMENT ON COLUMN remittance_rows.imported_raw_name IS '导入时的汇款表门店名，合并后仍留在原行上供对照。';

CREATE INDEX remittance_rows_store_idx ON remittance_rows (store_id);
CREATE INDEX remittance_rows_sheet_idx ON remittance_rows (sheet_id);

CREATE TABLE remittance_cells (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    row_id bigint NOT NULL REFERENCES remittance_rows (id) ON DELETE CASCADE,
    day integer NOT NULL,
    kind text NOT NULL,
    amount numeric(14, 2) NOT NULL,
    CONSTRAINT remittance_cells_day_check CHECK (day BETWEEN 1 AND 31),
    CONSTRAINT remittance_cells_kind_check CHECK (kind IN ('remit', 'ship')),
    CONSTRAINT remittance_cells_row_day_kind_unique UNIQUE (row_id, day, kind)
);

COMMENT ON TABLE remittance_cells IS '当天汇款或发货。单元格为空则不插入，和显式 0 区分。';

CREATE INDEX remittance_cells_row_idx ON remittance_cells (row_id);

CREATE TABLE shipment_orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES source_files (id) ON DELETE CASCADE,
    store_id bigint NOT NULL REFERENCES stores (id),
    order_index integer NOT NULL,
    biz_date date NOT NULL,
    customer_raw_name text NOT NULL,
    market_name text,
    phone text,
    address text,
    price_ratio text,
    ship_date_text text,
    CONSTRAINT shipment_orders_file_index_unique UNIQUE (source_file_id, order_index)
);

COMMENT ON COLUMN shipment_orders.biz_date IS '业务日，来自月份目录和文件名起始日，不采用单元格里可能被截断的日期。';
COMMENT ON COLUMN shipment_orders.customer_raw_name IS '这张订单上的客户名称原文。只改这一单时不改其他同名订单。';

CREATE INDEX shipment_orders_biz_date_idx ON shipment_orders (biz_date);
CREATE INDEX shipment_orders_store_idx ON shipment_orders (store_id);

CREATE TABLE shipment_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES shipment_orders (id) ON DELETE CASCADE,
    line_index integer NOT NULL,
    product_name text NOT NULL,
    unit text,
    order_qty numeric(14, 4),
    ship_qty numeric(14, 4),
    gift_qty numeric(14, 4),
    weight_total numeric(14, 4),
    actual_weight numeric(14, 4),
    gift_weight numeric(14, 4),
    actual_qty numeric(14, 4),
    unit_price numeric(14, 4),
    amount numeric(14, 2),
    CONSTRAINT shipment_lines_order_index_unique UNIQUE (order_id, line_index),
    CONSTRAINT shipment_lines_product_not_blank CHECK (btrim(product_name) <> '')
);

CREATE INDEX shipment_lines_order_idx ON shipment_lines (order_id);
