import argparse
import sys
from pathlib import Path
import json
import configparser
import psycopg2
from psycopg2.extras import RealDictCursor


def parse_cmd_line():
    usage = '''
Run a sql query against a postgres DB and format the result as a json file:

Requires configuration file for db connection string, by default it looks for 
./.psqldiff and ~/.psqldiff 

with the following configuration

[PSQL]
conn="postgresql://<DBUSER>:<DBPASSWRD>@<HOST>:<PORT>/<DBNAME>"

'''

    parse = argparse.ArgumentParser(description=usage)

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

from dataclasses import dataclass

def err(msg):
    print(f"Error: {msg}")
    sys.exit(1)

def find_conf(filename):
    current_dir = Path.cwd()
    file_path_current = current_dir / filename
    if file_path_current.exists():
        return file_path_current

    # Search in home directory
    home_dir = Path.home()
    file_path_home = home_dir / filename
    if file_path_home.exists():
        return file_path_home

    err(f"'{filename}' not found in current or home directory.")

def read_value(config, fpath, section, option):    
    if not config.has_section(section):
        err(f"Not section {section} in {fpath}]")
    if not config.has_option(section, option):
        err(f"Not {option} value in section {section} in {fpath}]")
    return config[section][option]


def read_conf():
    cfg_file = ".psqldiff"
    fpath = find_conf(cfg_file)
    config = configparser.ConfigParser()

    # Read the configuration file
    try:
        config.read(fpath)
        return read_value(config, fpath, 'PSQL', 'conf')
    except Exception as ex:
        err(f"Can't read configuration file {fpath} error: {ex}")

    err("wtf error")    

def db_connect(conn_str, read_only=True):
    conn = psycopg2.connect(conn_str, cursor_factory=RealDictCursor)
    conn.set_session(readonly=read_only, autocommit=True)
    return conn

def run_sql(conn, stmt):
    try:
        with conn.cursor() as cursor:
            
            cursor.execute(stmt)
            rows = cursor.fetchall()

            ret_rows = []
            for row in rows:
                ret_row = {}
                
                for column in row.items():
                    ret_row[column[0]] = column[1]

                ret_rows.append(ret_row)
            return ret_rows
    except Exception as e:
        err(f"failed to run query {stmt}, error: {e}")

def dump_sql(conn, stmt, file):

    row_data = run_sql(conn, stmt)

    with open(file, "w") as json_file:
        # Use json.dump() to write the data to the file
        json.dump(row_data, json_file, indent=4)

def main():
    opts, _ = parse_cmd_line()
    conn_str = read_conf()
    #print(f"conn_str: {conn_str}") 
    conn = db_connect(conn_str)

    ret_rows = dump_sql(conn, opts.query, opts.file)

main()

