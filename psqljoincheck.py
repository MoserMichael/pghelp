import argparse
import pprint
from dataclasses import dataclass
from sqlglot import parse_one, exp
import util as utl

debug_on = False

def parse_join_table(joined_table):
    tokens = joined_table.split(" ")

    if len(tokens) == 3:
        #if debug_on:
        #    print(f"parse_join_token: {joined_table} - {tokens}")
        if tokens[1].lower() == 'as':
            return True, tokens[0], tokens[2]
    
    error_msg = f"Can't analyse join table {joined_table}"
    return False, "", error_msg

@dataclass
class JoinClause:
    table_name: str
    joined_columns: list[str]


def ref_fields_from_joined_table(joined_table, join_condition):

    on_clause = join_condition.on() 
    if not on_clause:
        return None

    ref_column_names = []
    for col_in_condition in on_clause.find_all(exp.Column):
        ref_column_names.append(str(col_in_condition))

    # no variable references in join close -> don't need to check for missing index
    if len(ref_column_names) == 0:
        return None
    

    status, table_name, join_alias = parse_join_table(joined_table)
    if not status:
        return None

    ret = []
    for str_col in ref_column_names:    
        if str_col.startswith(join_alias):
            ret.append(str_col[ len(join_alias)+1 : ])
    

    return JoinClause(table_name = table_name, joined_columns=ret)

def get_table_indexes(conn, tbl_name):
    pos = tbl_name.find(".")
    schema_name = tbl_name[0:pos]
    table_n = tbl_name[(pos+1):]

    sql_stm = f"""
SELECT
    string_agg(a.attname, ', ' ORDER BY array_position(i.indkey, a.attnum)) AS indexed_columns,
    i.indisprimary AS is_pk,
    i.indisunique AS is_unique,
	pg_get_indexdef(i.indexrelid) AS index_definition_sql
FROM
    pg_catalog.pg_index i
JOIN
    pg_catalog.pg_class c ON c.oid = i.indrelid
INNER JOIN
    pg_catalog.pg_namespace n ON n.oid = c.relnamespace
-- Join to pg_attribute to access the column names using the physical attribute numbers (attnum)
JOIN
    pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
WHERE
    n.nspname = '{schema_name}' -- Replace 'public' with your schema name
    AND c.relname = '{table_n}' -- Replace 'table_1' with your table name
GROUP BY
    -- Group by the index properties, as string_agg is an aggregate function
    i.indexrelid, i.indisprimary, i.indisunique;
"""
            
    rows = utl.run_sql(conn, sql_stm)
    
    # make sets out of column sets
    for index_info in rows:
        index_info['indexed_columns_set'] = set(index_info['indexed_columns'].replace(' ', '').split(","))

    if debug_on:
        print(f"Indexes:\n{pprint.pformat(rows, indent=4)}")

    return rows
    
def find_matching_index(index_infos, joined_columns, error_messages):

    joined_column_set = set(joined_columns)
    if debug_on:
        print(f"find_matching_index: {joined_column_set}")

    # check if joined columns occur in any of the indexes.
    for index_info in index_infos:
        if index_info['indexed_columns_set'] == joined_column_set:
            return True, index_info['index_definition_sql']
        
    return False, ""

def check_join_clause(conn, join_clause_obj, error_messages):

    index_info = get_table_indexes(conn, join_clause_obj.table_name)

    match_info, index_sql = find_matching_index(index_info, join_clause_obj.joined_columns, error_messages)
    if not match_info:

        table_name_und = join_clause_obj.table_name.replace(".", "_")
        col_join_und = "_".join(join_clause_obj.joined_columns)
        col_join_comma = ",".join(join_clause_obj.joined_columns)

        create_index_stmt =f"CREATE INDEX idx_{table_name_und}_type_on_{col_join_und} ON {join_clause_obj.table_name}({col_join_comma});"
        msg = f"""Error: no matching index for join on {join_clause_obj.table_name} on table colums {join_clause_obj.joined_columns}
create statement: {create_index_stmt}
"""
        error_messages.insert(0,msg)
    else:
        msg = f"Info: matching index for join on {join_clause_obj.table_name}, matching index: {index_sql}"
        error_messages.append(msg)

    if debug_on:
        print(msg)



def get_select_stmt(sql_stmt):
    # Parse the SQL statement
    pexpr = parse_one(sql_stmt, read="postgres")

    if isinstance(pexpr, exp.Insert):
        sel = pexpr.find(exp.Select)
        if sel:
            return sel.sql()

    if isinstance(pexpr, exp.Select):
        return sql_stmt    
    
    utl.err("Can't handle sql statement (expected SELECT, or bulk INSERT / INSERT SELECT)")

    
def do_listing(msg):

    print("Listing:")
    line_num = 1
    for line in msg.split('\n'):
        print(f"{line_num}: {line}")
        line_num += 1


def check_joins_for_indexes(conn, sql_stmt, error_messages, show_listing):
    sql_stmt = get_select_stmt(sql_stmt)

    if show_listing:
        do_listing(sql_stmt)

    # Parse the SQL statement into an AST
    ast = parse_one(sql_stmt, read="postgres")

    # Find all join expressions in the AST
    joins = ast.find_all(exp.Join)

    for join in joins:

        # check if join over a subquery (don't need to handle)
        join_source = join.this
        
        # Check if the join source is a Subquery expression
        if isinstance(join_source, exp.Subquery):
            if debug_on:
                print(f"skipping: join over sub query {join.this.sql()}")
            continue

        # Get the join type (e.g., "join", "left join", "inner join")
        join_type = join.kind

        # Get the table being joined
        joined_table = join.this.sql()

        # Get the join condition (the ON clause expression)
        # join.args.get("on") returns the expression object for the ON clause
        join_condition = join.args.get("on")

        if debug_on:
            print("-" * 20)
            print(f"Join Type: {join_type}")
            print(f"Joined Table: {joined_table}")
            print(f"Join Condition: {join_condition.sql() if join_condition else 'None'}")
            print("")

        join_clause_obj = ref_fields_from_joined_table(joined_table, join)
        if not join_clause_obj:
            msg = f"Error: (internal) can't parse {joined_table}"
            print(msg)
            error_messages.append(msg)
            continue
        check_join_clause(conn, join_clause_obj, error_messages)

    
def parse_arguments():
    global debug_on

    usage = """Check if all join clauses are backed by indexes. 

Requires configuration file for db connection string, by default it looks for 
./.psqldiff and ~/.psqldiff 

with the following configuration

[PSQL]
conn="postgresql://<DBUSER>:<DBPASSWRD>@<HOST>:<PORT>/<DBNAME>"
    
"""

    parser = argparse.ArgumentParser(
        description=usage, formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument(
        "-i",
        "--input",  #
        help="input sql file",
        type=str,
        required=True
    ) 

    parser.add_argument(
        "-d",
        "--debug",  #
        help="debug on",
        action='store_true'
    )

    parser.add_argument(
        "-s",
        "--show_listing",  #
        help="show listing of sql",
        action='store_true'
    )

    ret = parser.parse_args()

    debug_on = ret.debug

    return ret


def test_main():
    args = parse_arguments()
    conn_str = utl.read_conf()

    conn = utl.db_connect(conn_str)
    with open(args.input, 'r') as in_file:
        sql_stmt = in_file.read().strip()
        error_messages = []

        check_joins_for_indexes(conn, sql_stmt, error_messages, show_listing=args.show_listing)

        for msg in error_messages:
            print(msg)

test_main()
