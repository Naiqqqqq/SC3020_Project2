-- Query 1
select *
from tpch.customer c
join tpch.orders o on c.c_custkey = o.o_custkey;

-- Query 2
select c.c_mktsegment, count(*) as cnt
from tpch.customer c
group by c.c_mktsegment
order by cnt desc;

-- Query 3
select o.o_orderpriority, count(*) as cnt
from tpch.orders o
where o.o_orderdate >= date '1995-01-01'
group by o.o_orderpriority
order by o.o_orderpriority;

-- Query 4
select l.l_returnflag, sum(l.l_extendedprice) as revenue
from tpch.lineitem l
where l.l_shipdate < date '1997-01-01'
group by l.l_returnflag
order by l.l_returnflag;

-- Query 5
select n.n_name, sum(o.o_totalprice) as total_sales
from tpch.nation n
join tpch.customer c on c.c_nationkey = n.n_nationkey
join tpch.orders o on o.o_custkey = c.c_custkey
group by n.n_name
order by total_sales desc
limit 10;
