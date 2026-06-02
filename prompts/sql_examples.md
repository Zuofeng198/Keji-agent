# SQL 分析模板 — 对账 / 数据比对 / 差异分析

写复杂 SQL 前先看这里，复制模板改表名和字段即可。

## 1. 两表对账（标准模式）

**场景**：A 系统与 B 系统按 ID 比对，找出缺失和金额不一致

```sql
SELECT
  COALESCE(a.id, b.id) AS id,
  a.amount AS sys_a_amount,
  b.amount AS sys_b_amount,
  CASE
    WHEN a.id IS NULL THEN 'B系统缺失'
    WHEN b.id IS NULL THEN 'A系统缺失'
    WHEN a.amount != b.amount THEN '金额不一致'
    ELSE '一致'
  END AS 比对结果,
  COALESCE(a.amount, 0) - COALESCE(b.amount, 0) AS 差异金额
FROM system_a a
FULL OUTER JOIN system_b b ON a.id = b.id
WHERE a.id IS NULL OR b.id IS NULL OR a.amount != b.amount
ORDER BY ABS(COALESCE(a.amount, 0) - COALESCE(b.amount, 0)) DESC
```

## 2. 三表对账（ERP × 银行 × 第三方）

**场景**：三套系统数据比对，标记缺失方和金额差异

```sql
-- 第一步：提取关键字段，统一ID格式
-- 银行流水摘要"销售收入X"→ 序号X
-- ERP订单号"ORD-202600XX" → 序号XX

-- 银行提取序号
SELECT CAST(regexp_extract(摘要, '\d+', 0) AS INTEGER) AS seq, *
FROM bank
WHERE 摘要 LIKE '销售收入%'

-- ERP提取序号  
SELECT CAST(substr(订单号, -2) AS INTEGER) AS seq, *
FROM erp

-- 第二步：ERP vs 银行 FULL JOIN
WITH erp_seq AS (
  SELECT *, CAST(substr(订单号, -2) AS INTEGER) AS seq FROM erp
),
bank_sales AS (
  SELECT *, CAST(regexp_extract(摘要, '\d+', 0) AS INTEGER) AS seq
  FROM bank WHERE 摘要 LIKE '销售收入%'
)
SELECT
  COALESCE(e.seq, b.seq) AS 序号,
  e.订单号, e.客户名, e.金额 AS ERP金额, e.支付方式,
  b.收入金额 AS 银行金额, b.交易日期 AS 银行日期,
  CASE
    WHEN e.订单号 IS NULL THEN 'ERP缺失'
    WHEN b.收入金额 IS NULL THEN '银行缺失'
    WHEN e.金额 != b.收入金额 THEN '金额不一致'
    ELSE '一致'
  END AS 比对结果,
  COALESCE(e.金额, 0) - COALESCE(b.收入金额, 0) AS 差异金额
FROM erp_seq e
FULL OUTER JOIN bank_sales b ON e.seq = b.seq
WHERE e.订单号 IS NULL OR b.收入金额 IS NULL OR e.金额 != b.收入金额
ORDER BY ABS(COALESCE(e.金额, 0) - COALESCE(b.收入金额, 0)) DESC
```

## 3. 分类汇总统计

**场景**：按差异类型分组统计数量和金额

```sql
SELECT
  比对结果,
  COUNT(*) AS 笔数,
  ROUND(SUM(ABS(差异金额)), 2) AS 涉及总金额
FROM (上面的对账SQL) AS diff
GROUP BY 比对结果
ORDER BY 涉及总金额 DESC
```

## 4. 支付方式调节表

**场景**：按支付方式汇总两系统差异

```sql
SELECT
  支付方式,
  COUNT(*) AS 订单数,
  ROUND(SUM(ERP金额), 2) AS ERP合计,
  ROUND(SUM(COALESCE(银行金额, 0)), 2) AS 银行合计,
  ROUND(SUM(差异金额), 2) AS 总差异
FROM (上面的对账SQL) AS diff
GROUP BY 支付方式
ORDER BY 总差异 DESC
```

## 5. 第三方支付手续费对账

**场景**：核对第三方支付的金额、手续费、实收金额三者关系

```sql
SELECT
  商户订单号, 金额, 手续费, 实收金额,
  ROUND(金额 - 手续费, 2) AS 应有实收,
  ROUND(实收金额 - (金额 - 手续费), 2) AS 差异
FROM third_pay
WHERE 状态 = '成功'
  AND ROUND(实收金额 - (金额 - 手续费), 2) != 0
```

## 6. DuckDB 实用技巧

```sql
-- 读取 CSV（已通过 mcp_quack_load_csv 加载，直接用表名）

-- 字符串提取数字
SELECT regexp_extract('销售收入123', '\d+', 0)  -- 返回 '123'

-- 取字符串末尾 N 位
SELECT substr('ORD-20260001', -2)  -- 返回 '01'

-- 类型转换
SELECT CAST('123' AS INTEGER)     -- 返回 123

-- 金额保留两位小数
SELECT ROUND(1234.5678, 2)        -- 返回 1234.57

-- NULL 处理
SELECT COALESCE(NULL, 0)          -- 返回 0
```
