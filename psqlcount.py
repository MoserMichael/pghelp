import argparse
import util as utl

def parse_cmd_line():
    usage = '''
Count number of rows in all tables of a given schema, report the result in sorted form.

Requires configuration file for db connection string, by default it looks for 
./.psqldiff and ~/.psqldiff 

with the following configuration

[PSQL]
conn="postgresql://<DBUSER>:<DBPASSWRD>@<HOST>:<PORT>/<DBNAME>"

'''

    parse = argparse.ArgumentParser(description=usage, formatter_class=argparse.RawDescriptionHelpFormatter)

    parse.add_argument('--schema', 
                       '-s', 
                       required=True,
                       type=str,
                       dest='schema', 
                       help='schema name')
    
    parse.add_argument('--fast', 
                       '-f', 
                       action='store_true',
                       required=False,
                       default=False,
                       dest='fast_count', 
                       help='show approximate count of rows (fast, but is not exact, falls back to slow count - if no count is known)')

    parse.add_argument('--verbose', 
                       '-v', 
                       action='store_true',
                       required=False,
                       default=False,
                       dest='verbose', 
                       help='show script progress, verbose output')

    return parse.parse_args(), parse



def count_table(conn, schema_and_table, fast_version, verbose):

    if verbose:
        print(f"-> Checking table {schema_and_table}")


    if not fast_version:
        query = f"""
SELECT count(*) AS row_count
FROM {schema_and_table.lower()}
"""    
    else:
        pos = schema_and_table.find(".")
        schema = schema_and_table[0:pos].lower()
        table = schema_and_table[(pos+1):].lower()

        query = f"""
SELECT c.reltuples AS row_count
FROM  pg_catalog.pg_class c
INNER JOIN
    pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN (
    SELECT 
        conrelid,
        conkey,
        contype
    FROM 
        pg_catalog.pg_constraint
) pk_info ON pk_info.conrelid = c.oid
WHERE
  n.nspname = '{schema}'
  AND c.relname = '{table}'
"""    
    try:
        row_count = 0
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                row_count = int(row['row_count'])
                break
        if verbose:
            print(f"-> {schema_and_table} has {row_count} rows")
        return row_count

    except Exception as e:
        utl.err(f"failed to get row count {e}")
    
def list_schema_tables(conn, schema_name):

    query = f"""
SELECT tablename
FROM pg_catalog.pg_tables
WHERE schemaname = '{schema_name.lower()}';
"""
                
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            ret = []
            for row in rows:
                ret.append(row['tablename'])
            return ret
    except Exception as e:
        utl.err(f"failed to list schemas {e}")
    

def count_tables_in_schema(schema_name, fast_version, verbose):
    conn_str = utl.read_conf()
    if verbose:
        print(f"connecting... {conn_str}")
    conn = utl.db_connect(conn_str)
    if verbose:
        print("-> connected")

    tbl_names = list_schema_tables(conn, schema_name)
    if verbose:
        print(f"-> Tables in schema {schema_name} : {','.join(tbl_names)}")

    list_tbls = []
    for tbl_name in tbl_names:
        full_name=f"{schema_name}.{tbl_name}"
        cnt = count_table(conn, full_name, fast_version, verbose)
        if cnt == -1 and fast_version:
            cnt = count_table(conn, full_name, False, verbose)

        list_tbls.append( (cnt, full_name) )
    
    list_tbls.sort(key=lambda arg: arg[0])
    for entry in list_tbls:
        print(f"row_count: {entry[0]} table: {entry[1]}")

def main():
    arg, _ = parse_cmd_line()
    count_tables_in_schema(arg.schema, arg.fast_count, arg.verbose)

main()

