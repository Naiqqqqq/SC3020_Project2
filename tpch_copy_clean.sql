-- Absolute paths for local TPC-H .tbl files.

\copy tpch.region   from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/region.tbl' with (format text, delimiter '|');
\copy tpch.nation   from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/nation.tbl' with (format text, delimiter '|');
\copy tpch.supplier from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/supplier.tbl' with (format text, delimiter '|');
\copy tpch.customer from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/customer.tbl' with (format text, delimiter '|');
\copy tpch.part     from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/part.tbl' with (format text, delimiter '|');
\copy tpch.partsupp from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/partsupp.tbl' with (format text, delimiter '|');
\copy tpch.orders   from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/orders.tbl' with (format text, delimiter '|');
\copy tpch.lineitem from 'C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/lineitem.tbl' with (format text, delimiter '|');


