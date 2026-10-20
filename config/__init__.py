import pymysql

# Use PyMySQL (pure Python) as the MySQLdb driver so builds don't need
# MySQL C headers (e.g. on Vercel). Django checks the mysqlclient version,
# so report one it accepts.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()
