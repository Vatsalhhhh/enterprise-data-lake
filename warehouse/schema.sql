-- Star schema for the cross-domain warehouse.
-- Shared dimensions (dim_date, dim_department, dim_region) let every
-- per-domain fact table join on the same grain, which is what makes
-- cross-domain views (revenue vs HR cost, marketing spend vs sales lift,
-- inventory turns vs sales velocity) possible with a single JOIN.

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- ============ DIMENSIONS ============

CREATE TABLE dim_date (
    date_key        DATE PRIMARY KEY,
    year            INT NOT NULL,
    month           INT NOT NULL,
    month_start     DATE NOT NULL,
    quarter         INT NOT NULL,
    month_name      VARCHAR(20) NOT NULL
);

CREATE TABLE dim_department (
    department      VARCHAR(50) PRIMARY KEY
);

CREATE TABLE dim_region (
    region_code     VARCHAR(20) PRIMARY KEY,
    country_group   VARCHAR(50),
    sub_region      VARCHAR(50)
);

-- ============ FACT TABLES ============

CREATE TABLE fact_sales (
    order_id        VARCHAR(20) PRIMARY KEY,
    customer_id     VARCHAR(20),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    order_date      DATE,
    month_start     DATE,
    order_total     NUMERIC(14,2),
    order_cost      NUMERIC(14,2),
    status          VARCHAR(20)
);

CREATE TABLE fact_hr_cost (
    department      VARCHAR(50) REFERENCES dim_department(department),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    headcount       INT,
    salary_cost     NUMERIC(14,2),
    benefits_cost   NUMERIC(14,2),
    total_cost      NUMERIC(14,2),
    PRIMARY KEY (department, region_code, month_start)
);

CREATE TABLE fact_finance_gl (
    txn_id          VARCHAR(20) PRIMARY KEY,
    department      VARCHAR(50) REFERENCES dim_department(department),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    account_code    VARCHAR(10),
    account_name    VARCHAR(50),
    amount          NUMERIC(14,2)
);

CREATE TABLE fact_inventory_movement (
    movement_id     VARCHAR(20) PRIMARY KEY,
    sku             VARCHAR(20),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    movement_type   VARCHAR(20),
    quantity        INT
);

CREATE TABLE fact_inventory_stock (
    sku             VARCHAR(20),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    quantity_on_hand INT,
    unit_cost       NUMERIC(10,2),
    PRIMARY KEY (sku, region_code, month_start)
);

CREATE TABLE fact_marketing_spend (
    campaign_id     VARCHAR(20) PRIMARY KEY,
    channel         VARCHAR(30),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    spend_amount    NUMERIC(14,2)
);

CREATE TABLE fact_marketing_leads (
    lead_id         VARCHAR(20) PRIMARY KEY,
    campaign_id     VARCHAR(20),
    region_code     VARCHAR(20) REFERENCES dim_region(region_code),
    month_start     DATE,
    converted       BOOLEAN
);

CREATE TABLE fact_finance_budget (
    department      VARCHAR(50) REFERENCES dim_department(department),
    month_start     DATE,
    budget_amount    NUMERIC(14,2),
    PRIMARY KEY (department, month_start)
);

-- ============ CROSS-DOMAIN VIEWS ============

-- Revenue vs HR cost by department/region/month (finer grain, used to
-- surface the engineered Customer Support / NA-EAST story). Both sides
-- are pre-aggregated to the join grain before joining, so the join
-- itself is one-to-one and cannot fan out row counts.
CREATE OR REPLACE VIEW vw_revenue_vs_hr_cost_by_region AS
WITH hr AS (
    SELECT department, region_code, month_start, SUM(total_cost) AS hr_cost
    FROM fact_hr_cost
    GROUP BY department, region_code, month_start
),
gl AS (
    SELECT department, region_code, month_start,
           SUM(amount) FILTER (WHERE account_code = '4000') AS gl_revenue,
           -SUM(amount) FILTER (WHERE account_code = '5000') AS cogs
    FROM fact_finance_gl
    GROUP BY department, region_code, month_start
)
SELECT
    hr.department,
    hr.region_code,
    hr.month_start,
    hr.hr_cost,
    COALESCE(gl.gl_revenue, 0) AS gl_revenue,
    COALESCE(gl.cogs, 0) AS cogs,
    COALESCE(gl.gl_revenue, 0) - COALESCE(gl.cogs, 0) AS gross_margin
FROM hr
LEFT JOIN gl ON gl.department = hr.department AND gl.region_code = hr.region_code AND gl.month_start = hr.month_start
ORDER BY hr.department, hr.region_code, hr.month_start;

-- Revenue vs HR cost by department/month (rolled up across regions)
CREATE OR REPLACE VIEW vw_revenue_vs_hr_cost AS
SELECT
    department,
    month_start,
    SUM(hr_cost) AS hr_cost,
    SUM(gl_revenue) AS gl_revenue,
    SUM(cogs) AS cogs,
    SUM(gross_margin) AS gross_margin
FROM vw_revenue_vs_hr_cost_by_region
GROUP BY department, month_start
ORDER BY department, month_start;

-- Marketing spend vs sales lift by region/month
CREATE OR REPLACE VIEW vw_marketing_spend_vs_sales AS
SELECT
    COALESCE(m.region_code, s.region_code) AS region_code,
    COALESCE(m.month_start, s.month_start) AS month_start,
    COALESCE(m.spend, 0) AS marketing_spend,
    COALESCE(s.sales_revenue, 0) AS sales_revenue,
    COALESCE(s.order_count, 0) AS order_count
FROM (
    SELECT region_code, month_start, SUM(spend_amount) AS spend
    FROM fact_marketing_spend GROUP BY region_code, month_start
) m
FULL OUTER JOIN (
    SELECT region_code, month_start, SUM(order_total) AS sales_revenue, COUNT(*) AS order_count
    FROM fact_sales WHERE status <> 'cancelled' GROUP BY region_code, month_start
) s ON m.region_code = s.region_code AND m.month_start = s.month_start
ORDER BY region_code, month_start;

-- Inventory turns vs sales velocity by sku/region/month
CREATE OR REPLACE VIEW vw_inventory_turns_vs_sales AS
SELECT
    i.sku,
    i.region_code,
    i.month_start,
    i.quantity_on_hand,
    COALESCE(out_mv.outbound_qty, 0) AS outbound_qty,
    CASE WHEN i.quantity_on_hand > 0
         THEN ROUND(COALESCE(out_mv.outbound_qty, 0)::NUMERIC / i.quantity_on_hand, 3)
         ELSE NULL END AS turnover_ratio
FROM fact_inventory_stock i
LEFT JOIN (
    SELECT sku, region_code, month_start, SUM(quantity) AS outbound_qty
    FROM fact_inventory_movement WHERE movement_type = 'outbound'
    GROUP BY sku, region_code, month_start
) out_mv ON out_mv.sku = i.sku AND out_mv.region_code = i.region_code AND out_mv.month_start = i.month_start
ORDER BY i.sku, i.region_code, i.month_start;

-- Department-level P&L combining budget, actuals and headcount cost
CREATE OR REPLACE VIEW vw_department_pnl AS
SELECT
    g.department,
    g.month_start,
    COALESCE(SUM(g.amount) FILTER (WHERE g.account_code = '4000'), 0) AS revenue,
    COALESCE(-SUM(g.amount) FILTER (WHERE g.account_code != '4000'), 0) AS total_opex,
    b.budget_amount,
    h.total_cost AS hr_cost
FROM fact_finance_gl g
LEFT JOIN fact_finance_budget b ON b.department = g.department AND b.month_start = g.month_start
LEFT JOIN (
    SELECT department, month_start, SUM(total_cost) AS total_cost
    FROM fact_hr_cost GROUP BY department, month_start
) h ON h.department = g.department AND h.month_start = g.month_start
GROUP BY g.department, g.month_start, b.budget_amount, h.total_cost
ORDER BY g.department, g.month_start;
