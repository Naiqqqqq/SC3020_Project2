SET search_path TO tpch;

ALTER TABLE region
    ADD PRIMARY KEY (r_regionkey);

ALTER TABLE nation
    ADD PRIMARY KEY (n_nationkey);

ALTER TABLE nation
    ADD CONSTRAINT nation_fk1
    FOREIGN KEY (n_regionkey) REFERENCES region;

ALTER TABLE part
    ADD PRIMARY KEY (p_partkey);

ALTER TABLE supplier
    ADD PRIMARY KEY (s_suppkey);

ALTER TABLE supplier
    ADD CONSTRAINT supplier_fk1
    FOREIGN KEY (s_nationkey) REFERENCES nation;

ALTER TABLE partsupp
    ADD PRIMARY KEY (ps_partkey, ps_suppkey);

ALTER TABLE customer
    ADD PRIMARY KEY (c_custkey);

ALTER TABLE customer
    ADD CONSTRAINT customer_fk1
    FOREIGN KEY (c_nationkey) REFERENCES nation;

ALTER TABLE orders
    ADD PRIMARY KEY (o_orderkey);

ALTER TABLE orders
    ADD CONSTRAINT orders_fk1
    FOREIGN KEY (o_custkey) REFERENCES customer;

ALTER TABLE lineitem
    ADD PRIMARY KEY (l_orderkey, l_linenumber);

ALTER TABLE partsupp
    ADD CONSTRAINT partsupp_fk1
    FOREIGN KEY (ps_suppkey) REFERENCES supplier;

ALTER TABLE partsupp
    ADD CONSTRAINT partsupp_fk2
    FOREIGN KEY (ps_partkey) REFERENCES part;

ALTER TABLE lineitem
    ADD CONSTRAINT lineitem_fk1
    FOREIGN KEY (l_orderkey) REFERENCES orders;

ALTER TABLE lineitem
    ADD CONSTRAINT lineitem_fk2
    FOREIGN KEY (l_partkey, l_suppkey) REFERENCES partsupp;
