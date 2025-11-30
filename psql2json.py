import argparse
import json
from dataclasses import dataclass
import datetime
from psycopg2.extras import RealDictCursor
import util as utl


def parse_cmd_line():
    usage = '''
Run a sql query against a postgres DB and format the result as a json file:

Requires configuration file for db connection string, by default it looks for 
./.psqldiff and ~/.psqldiff 

with the following configuration

[PSQL]
conn="postgresql://<DBUSER>:<DBPASSWRD>@<HOST>:<PORT>/<DBNAME>"

'''

    parse = argparse.ArgumentParser(description=usage, formatter_class=argparse.RawDescriptionHelpFormatter)

    parse.add_argument('--query', 
                       '-q', 
                       required=True,
                       type=str,
                       dest='query', 
                       help='SQL query to run')

    parse.add_argument('--file', 
                       '-f', 
                       required=True,
                       type=str,
                       dest='file', 
                       help='output json file')

    return parse.parse_args(), parse


def run_sql(conn, stmt):
    try:
        with conn.cursor() as cursor:
            
            cursor.execute(stmt)
            rows = cursor.fetchall()

            ret_rows = []
            for row in rows:
                ret_row = {}
                
                for column in row.items():
                    if isinstance(column[1], datetime.datetime):
                        column  = (column[0], column[1].strftime("%m-%d-%Y %H:%M:%S"))
                    ret_row[column[0]] = column[1]

                ret_rows.append(ret_row)
            return ret_rows
    except Exception as e:
        utl.err(f"failed to run query {stmt}, error: {e}")

def dump_sql(conn, stmt, file):

    row_data = run_sql(conn, stmt)

    with open(file, "w") as json_file:
        # Use json.dump() to write the data to the file
        json.dump(row_data, json_file, indent=4)

def main():
    opts, _ = parse_cmd_line()
    conn_str = utl.read_conf()
    #print(f"conn_str: {conn_str}") 
    conn = utl.db_connect(conn_str)
    dump_sql(conn, opts.query, opts.file)

main()

