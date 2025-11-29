import argparse
import sys
from pathlib import Path
import configparser
import psycopg2
from psycopg2.extras import RealDictCursor


# map value of pg_catalog.pg_constraint.contype  
map_constraint_to_name = {
    'p': 'PRIMARY KEY',
    'u': 'UNIQUE',
    'f': 'FOREIGN KEY',
    'c': 'CHECK',
    't': 'TRIGGER',
    'x': 'EXCLUSION'
}

def parse_cmd_line():
    usage = '''
Compare the structure of two SQL tables in postgres DB

Requires configuration file for db connection string, by default it looks for 
./.psqldiff and ~/.psqldiff 

with the following configuration

[PSQL]
conn="postgresql://<DBUSER>:<DBPASSWRD>@<HOST>:<PORT>/<DBNAME>"

'''

    parse = argparse.ArgumentParser(description=usage, formatter_class=argparse.RawDescriptionHelpFormatter)

    parse.add_argument('--table1', 
                       '-f', 
                       required=True,
                       type=str,
                       dest='table1', 
                       help='table name to compare (can include schema name)')

    parse.add_argument('--table2', 
                       '-t', 
                       required=True,
                       type=str,
                       dest='table2', 
                       help='table name to compare (can include schema name)')

    parse.add_argument('--common', 
                       '-s', 
                       action='store_true',
                       required=False,
                       default=False,
                       dest='show_common', 
                       help='show common columns')

    return parse.parse_args(), parse

from dataclasses import dataclass

@dataclass
class ColEntry:
    idx_num:  int
    col_name: str
    col_type: str
    con_type: str

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

def get_schema_and_table(dot_name):
    dot_pos = dot_name.find(".")
    if dot_pos != -1:
        schema_name = dot_name[0:dot_pos] 
        tbl_name = dot_name[dot_pos+1:]
    else:
        schema_name = "public"
        tbl_name = dot_name
    
    return schema_name, tbl_name
    

def get_constraint_name(constraint):
    if constraint in map_constraint_to_name:
        return map_constraint_to_name[constraint]
    return f"? {constraint} ?"

def get_columns(conn, schema_and_tbl):
    try:

        schema_name, tbl_name = get_schema_and_table(schema_and_tbl)

        # get list of fields in source view
        with conn.cursor() as cursor:
            stmt = f"""
SELECT
    a.attnum  AS column_idx,
    a.attname AS column_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
    pk_info.contype AS constraint_type
FROM
    pg_catalog.pg_attribute a
INNER JOIN
    pg_catalog.pg_class c ON c.oid = a.attrelid
INNER JOIN
    pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN (
    SELECT
        conrelid,
        conkey,
        contype
    FROM
        pg_catalog.pg_constraint
) pk_info ON pk_info.conrelid = c.oid AND a.attnum = ANY(pk_info.conkey)
WHERE
    n.nspname = '{schema_name}' -- Replace with your schema name (e.g., 'public')
    AND c.relname = '{tbl_name}' -- Replace with your table name
    AND a.attnum > 0
    AND NOT a.attisdropped
ORDER BY
    a.attnum;
"""
            cursor.execute(stmt)
            rows = cursor.fetchall()
            ret = []
            for r in rows:
                orig = data_type_full = r['data_type']
                e = ColEntry(idx_num=r['column_idx'], col_name=r['column_name'], col_type = r['data_type'], con_type=r['constraint_type'])


                #if "(" in data_type_full:
                #    matchAll = re.match(r"^.*\(([^\)+]*)\).*$", #data_type_full)
                #    match = re.match(r"^.*\((\d+\)).*$", data_type_full)
                #    if matchAll and not match:
                #        idx = data_type_full.index("(")
                #        if idx != -1:
                #            data_type_full = data_type_full[0:idx]

                ret.append(e)
                
            #print(f"type info for {schema_and_tbl} : {ret}")
            return ret
    except Exception as e:
        err(f"failed to get field types for {schema_and_tbl} err {e}" )

    
def db_connect(conn_str, read_only=True):
    conn = psycopg2.connect(conn_str, cursor_factory=RealDictCursor)
    conn.set_session(readonly=read_only, autocommit=True)
    return conn

def make_dict(col_type_list):
    ret = {}
    for col in col_type_list:
        ret[col.col_name] = col
    return ret

def compare_it(tbl1, col_type_list1, tbl2, col_type_list2, show_common):
    col_dict1 = make_dict(col_type_list1)
    col_dict2 = make_dict(col_type_list2)

    cols_with_same_name_and_type =[]
    cols_with_same_name_diff_type = []

    for col in col_type_list1:
        if col.col_name in col_dict2:
            col2 = col_dict2.get(col.col_name)
            if col2:
                if col.col_type == col2.col_type and col.con_type == col2.con_type:
                    cols_with_same_name_and_type.append( (col, col2) )
                else:
                    cols_with_same_name_diff_type.append( (col, col2) )

                del col_dict2[ col.col_name ]
                del col_dict1[ col.col_name ]

    print_column_diff_report(tbl1, tbl2, cols_with_same_name_and_type, cols_with_same_name_diff_type, col_dict1, col_dict2, show_common)

def show_columns_with_type_changed(tbl1, tbl2, cols_with_same_name_diff_type):
    if len(cols_with_same_name_diff_type) != 0:
        print("COLUMNS WITH IDENTICAL NAMES AND CHANGED TYPES, OR CONSTRAINTS")
        print("")
        for e in cols_with_same_name_diff_type:
            print(f"column: {e[0].col_name}")
            report_common = ""
            report_left = ""
            report_right = ""

            #print(f"{tbl1}: {e[0].col_type} constr: {e[0].con_type}; {tbl2}: {e[1].col_type} constr: {e[1].con_type};")

            if e[0].col_type != e[1].col_type:
                report_left  = f"\ttable: {tbl1} of type: {e[0].col_type}\n"
                report_right = f"\ttable: {tbl2} of type: {e[1].col_type}\n"
            else:
                report_common = f"\ttable: {tbl1} and {tbl2} of type: {e[0].col_type}\n"

            if str(e[0].con_type) != str(e[1].con_type):
                if e[0].con_type:
                    report_left  += f"\ttable: {tbl1} of constraint: {get_constraint_name(e[0].con_type)}\n"
                if e[1].con_type:
                    report_right += f"\ttable: {tbl2} of constraint: {get_constraint_name(e[1].con_type)}\n"
            else:
                pass

            msg=f"{report_common}{report_left}{report_right}"
            if len(msg):
                msg = msg[0:len(msg)-1]
            print(msg)
            print("")

def show_cols_common(tbl1, tbls2, cols_with_same_name_and_type):
    if len(cols_with_same_name_and_type):
        print(f"COLUMN NAMES THAT APPEAR IN BOTH TABLES WITH IDENTICAL TYPE AND CONSTRAINT")
        print("")
        for e in cols_with_same_name_and_type:
            print(f"\tcolumn: {e[0].col_name} with type: {e[0].col_type}")

def show_cols_exclusive(tbl_name, col_exclusive):
    if len(col_exclusive):
        print(f"COLUMN NAMES THAT APPEAR IN TABLE {tbl_name} ONLY")
        print("")
        for _, e in col_exclusive.items():
            constr = ""
            if e.con_type:
                constr = f"constraint: {get_constraint_name(e.con_type)}"
            print(f"\tcolumn: {e.col_name} with type: {e.col_type}  {constr}") # appears only in table: {tbl_name}")
        print("") 

def print_column_diff_report(tbl1, tbl2, cols_with_same_name_and_type,cols_with_same_name_diff_type, col_dict1, col_dict2, show_common):   
    if len(col_dict1) == 0 and len(col_dict2) == 0:
        if len(cols_with_same_name_diff_type) == 0:
            print(f"{tbl1} and {tbl2} have identical columns and with identical types")
            return
    
    show_columns_with_type_changed(tbl1, tbl2, cols_with_same_name_diff_type)

    show_cols_exclusive(tbl1, col_dict1)
    show_cols_exclusive(tbl2, col_dict2)    

    if show_common:
        show_cols_common(tbl1, tbl2, cols_with_same_name_and_type)
        
    

def diff_tables(conn, tbl1, tbl2, show_common):
    print(f"compare tables: {tbl1}, {tbl2}")
    col_type_list1 = get_columns(conn, tbl1)
    col_type_list2 = get_columns(conn, tbl2)

    compare_it(tbl1, col_type_list1, tbl2, col_type_list2, show_common)

def main():
    opts, _ = parse_cmd_line()
    conn_str = read_conf()
    #print(f"conn_str: {conn_str}") 
    conn = db_connect(conn_str)

    diff_tables(conn, opts.table1, opts.table2, opts.show_common)


main()

