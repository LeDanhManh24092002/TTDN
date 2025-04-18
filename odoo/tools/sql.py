# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

# pylint: disable=sql-injection

import logging
import psycopg2

_schema = logging.getLogger('odoo.schema')

_CONFDELTYPES = {
    'RESTRICT': 'r',
    'NO ACTION': 'a',
    'CASCADE': 'c',
    'SET NULL': 'n',
    'SET DEFAULT': 'd',
}

def existing_tables(cr, tablenames):
    """ Return the names of existing tables among ``tablenames``. """
    query = """
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON (n.oid = c.relnamespace)
         WHERE c.relname IN %s
           AND c.relkind IN ('r', 'v', 'm')
           AND n.nspname = current_schema
    """
    cr.execute(query, [tuple(tablenames)])
    return [row[0] for row in cr.fetchall()]

def table_exists(cr, tablename):
    """ Return whether the given table exists. """
    return len(existing_tables(cr, {tablename})) == 1

def table_kind(cr, tablename):
    """ Return the kind of a table: ``'r'`` (regular table), ``'v'`` (view),
        ``'f'`` (foreign table), ``'t'`` (temporary table),
        ``'m'`` (materialized view), or ``None``.
    """
    query = """
        SELECT c.relkind
          FROM pg_class c
          JOIN pg_namespace n ON (n.oid = c.relnamespace)
         WHERE c.relname = %s
           AND n.nspname = current_schema
    """
    cr.execute(query, (tablename,))
    return cr.fetchone()[0] if cr.rowcount else None

def create_model_table(cr, tablename, comment=None, columns=()):
    """ Create the table for a model. """
    colspecs = ['id SERIAL NOT NULL'] + [
        '"{}" {}'.format(columnname, columntype)
        for columnname, columntype, columncomment in columns
    ]
    cr.execute('CREATE TABLE "{}" ({}, PRIMARY KEY(id))'.format(tablename, ", ".join(colspecs)))

    queries, params = [], []
    if comment:
        queries.append('COMMENT ON TABLE "{}" IS %s'.format(tablename))
        params.append(comment)
    for columnname, columntype, columncomment in columns:
        queries.append('COMMENT ON COLUMN "{}"."{}" IS %s'.format(tablename, columnname))
        params.append(columncomment)
    if queries:
        cr.execute("; ".join(queries), params)

    _schema.debug("Table %r: created", tablename)

def table_columns(cr, tablename):
    """ Return a dict mapping column names to their configuration. The latter is
        a dict with the data from the table ``information_schema.columns``.
    """
    # Do not select the field `character_octet_length` from `information_schema.columns`
    # because specific access right restriction in the context of shared hosting (Heroku, OVH, ...)
    # might prevent a postgres user to read this field.
    query = '''SELECT column_name, udt_name, character_maximum_length, is_nullable
               FROM information_schema.columns WHERE table_name=%s'''
    cr.execute(query, (tablename,))
    return {row['column_name']: row for row in cr.dictfetchall()}

def column_exists(cr, tablename, columnname):
    """ Return whether the given column exists. """
    query = """ SELECT 1 FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s """
    cr.execute(query, (tablename, columnname))
    return cr.rowcount

def create_column(cr, tablename, columnname, columntype, comment=None):
    """ Create a column with the given type. """
    coldefault = (columntype.upper()=='BOOLEAN') and 'DEFAULT false' or ''
    cr.execute('ALTER TABLE "{}" ADD COLUMN "{}" {} {}'.format(tablename, columnname, columntype, coldefault))
    if comment:
        cr.execute('COMMENT ON COLUMN "{}"."{}" IS %s'.format(tablename, columnname), (comment,))
    _schema.debug("Table %r: added column %r of type %s", tablename, columnname, columntype)

def rename_column(cr, tablename, columnname1, columnname2):
    """ Rename the given column. """
    cr.execute('ALTER TABLE "{}" RENAME COLUMN "{}" TO "{}"'.format(tablename, columnname1, columnname2))
    _schema.debug("Table %r: renamed column %r to %r", tablename, columnname1, columnname2)

def convert_column(cr, tablename, columnname, columntype):
    """ Convert the column to the given type. """
    try:
        with cr.savepoint(flush=False):
            cr.execute('ALTER TABLE "{}" ALTER COLUMN "{}" TYPE {}'.format(tablename, columnname, columntype),
                       log_exceptions=False)
    except psycopg2.NotSupportedError:
        # can't do inplace change -> use a casted temp column
        query = '''
            ALTER TABLE "{0}" RENAME COLUMN "{1}" TO __temp_type_cast;
            ALTER TABLE "{0}" ADD COLUMN "{1}" {2};
            UPDATE "{0}" SET "{1}"= __temp_type_cast::{2};
            ALTER TABLE "{0}" DROP COLUMN  __temp_type_cast CASCADE;
        '''
        cr.execute(query.format(tablename, columnname, columntype))
    _schema.debug("Table %r: column %r changed to type %s", tablename, columnname, columntype)

def set_not_null(cr, tablename, columnname):
    """ Add a NOT NULL constraint on the given column. """
    query = 'ALTER TABLE "{}" ALTER COLUMN "{}" SET NOT NULL'.format(tablename, columnname)
    try:
        with cr.savepoint(flush=False):
            cr.execute(query, log_exceptions=False)
            _schema.debug("Table %r: column %r: added constraint NOT NULL", tablename, columnname)
    except Exception:
        raise Exception("Table %r: unable to set NOT NULL on column %r", tablename, columnname)

def drop_not_null(cr, tablename, columnname):
    """ Drop the NOT NULL constraint on the given column. """
    cr.execute('ALTER TABLE "{}" ALTER COLUMN "{}" DROP NOT NULL'.format(tablename, columnname))
    _schema.debug("Table %r: column %r: dropped constraint NOT NULL", tablename, columnname)

def constraint_definition(cr, tablename, constraintname):
    """ Return the given constraint's definition. """
    query = """
        SELECT COALESCE(d.description, pg_get_constraintdef(c.oid))
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        LEFT JOIN pg_description d ON c.oid = d.objoid
        WHERE t.relname = %s AND conname = %s;"""
    cr.execute(query, (tablename, constraintname))
    return cr.fetchone()[0] if cr.rowcount else None

def add_constraint(cr, tablename, constraintname, definition):
    """ Add a constraint on the given table. """
    query1 = 'ALTER TABLE "{}" ADD CONSTRAINT "{}" {}'.format(tablename, constraintname, definition)
    query2 = 'COMMENT ON CONSTRAINT "{}" ON "{}" IS %s'.format(constraintname, tablename)
    try:
        with cr.savepoint(flush=False):
            cr.execute(query1, log_exceptions=False)
            cr.execute(query2, (definition,), log_exceptions=False)
            _schema.debug("Table %r: added constraint %r as %s", tablename, constraintname, definition)
    except Exception:
        raise Exception("Table %r: unable to add constraint %r as %s", tablename, constraintname, definition)

def drop_constraint(cr, tablename, constraintname):
    """ drop the given constraint. """
    try:
        with cr.savepoint(flush=False):
            cr.execute('ALTER TABLE "{}" DROP CONSTRAINT "{}"'.format(tablename, constraintname))
            _schema.debug("Table %r: dropped constraint %r", tablename, constraintname)
    except Exception:
        _schema.warning("Table %r: unable to drop constraint %r!", tablename, constraintname)

def add_foreign_key(cr, tablename1, columnname1, tablename2, columnname2, ondelete):
    """ Create the given foreign key, and return ``True``. """
    query = 'ALTER TABLE "{}" ADD FOREIGN KEY ("{}") REFERENCES "{}"("{}") ON DELETE {}'
    cr.execute(query.format(tablename1, columnname1, tablename2, columnname2, ondelete))
    _schema.debug("Table %r: added foreign key %r references %r(%r) ON DELETE %s",
                  tablename1, columnname1, tablename2, columnname2, ondelete)
    return True

def get_foreign_keys(cr, tablename1, columnname1, tablename2, columnname2, ondelete):
    cr.execute(
        """
            SELECT fk.conname as name
            FROM pg_constraint AS fk
            JOIN pg_class AS c1 ON fk.conrelid = c1.oid
            JOIN pg_class AS c2 ON fk.confrelid = c2.oid
            JOIN pg_attribute AS a1 ON a1.attrelid = c1.oid AND fk.conkey[1] = a1.attnum
            JOIN pg_attribute AS a2 ON a2.attrelid = c2.oid AND fk.confkey[1] = a2.attnum
            WHERE fk.contype = 'f'
            AND c1.relname = %s
            AND a1.attname = %s
            AND c2.relname = %s
            AND a2.attname = %s
            AND fk.confdeltype = %s
        """, [tablename1, columnname1, tablename2, columnname2, _CONFDELTYPES[ondelete.upper()]]
    )
    return [r[0] for r in cr.fetchall()]

def fix_foreign_key(cr, tablename1, columnname1, tablename2, columnname2, ondelete):
    """ Update the foreign keys between tables to match the given one, and
        return ``True`` if the given foreign key has been recreated.
    """
    # Do not use 'information_schema' here, as those views are awfully slow!
    deltype = _CONFDELTYPES.get(ondelete.upper(), 'a')
    query = """ SELECT con.conname, c2.relname, a2.attname, con.confdeltype as deltype
                  FROM pg_constraint as con, pg_class as c1, pg_class as c2,
                       pg_attribute as a1, pg_attribute as a2
                 WHERE con.contype='f' AND con.conrelid=c1.oid AND con.confrelid=c2.oid
                   AND array_lower(con.conkey, 1)=1 AND con.conkey[1]=a1.attnum
                   AND array_lower(con.confkey, 1)=1 AND con.confkey[1]=a2.attnum
                   AND a1.attrelid=c1.oid AND a2.attrelid=c2.oid
                   AND c1.relname=%s AND a1.attname=%s """
    cr.execute(query, (tablename1, columnname1))
    found = False
    for fk in cr.fetchall():
        if not found and fk[1:] == (tablename2, columnname2, deltype):
            found = True
        else:
            drop_constraint(cr, tablename1, fk[0])
    if not found:
        return add_foreign_key(cr, tablename1, columnname1, tablename2, columnname2, ondelete)

def index_exists(cr, indexname):
    """ Return whether the given index exists. """
    cr.execute("SELECT 1 FROM pg_indexes WHERE indexname=%s", (indexname,))
    return cr.rowcount

def create_index(cr, indexname, tablename, expressions):
    """ Create the given index unless it exists. """
    if index_exists(cr, indexname):
        return
    args = ', '.join(expressions)
    cr.execute('CREATE INDEX "{}" ON "{}" ({})'.format(indexname, tablename, args))
    _schema.debug("Table %r: created index %r (%s)", tablename, indexname, args)

def create_unique_index(cr, indexname, tablename, expressions):
    """ Create the given index unless it exists. """
    if index_exists(cr, indexname):
        return
    args = ', '.join(expressions)
    cr.execute('CREATE UNIQUE INDEX "{}" ON "{}" ({})'.format(indexname, tablename, args))
    _schema.debug("Table %r: created index %r (%s)", tablename, indexname, args)

def drop_index(cr, indexname, tablename):
    """ Drop the given index if it exists. """
    cr.execute('DROP INDEX IF EXISTS "{}"'.format(indexname))
    _schema.debug("Table %r: dropped index %r", tablename, indexname)

def drop_view_if_exists(cr, viewname):
    kind = table_kind(cr, viewname)
    if kind == 'v':
        cr.execute("DROP VIEW {} CASCADE".format(viewname))
    elif kind == 'm':
        cr.execute("DROP MATERIALIZED VIEW {} CASCADE".format(viewname))

def escape_psql(to_escape):
    return to_escape.replace('\\', r'\\').replace('%', r'\%').replace('_', r'\_')

def pg_varchar(size=0):
    """ Returns the VARCHAR declaration for the provided size:

    * If no size (or an empty or negative size is provided) return an
      'infinite' VARCHAR
    * Otherwise return a VARCHAR(n)

    :type int size: varchar size, optional
    :rtype: str
    """
    if size:
        if not isinstance(size, int):
            raise ValueError("VARCHAR parameter should be an int, got %s" % type(size))
        if size > 0:
            return 'VARCHAR(%d)' % size
    return 'VARCHAR'

def reverse_order(order):
    """ Reverse an ORDER BY clause """
    items = []
    for item in order.split(','):
        item = item.lower().split()
        direction = 'asc' if item[1:] == ['desc'] else 'desc'
        items.append('%s %s' % (item[0], direction))
    return ', '.join(items)


def increment_field_skiplock(record, field):
    """
        Increment 'friendly' the [field] of the current [record](s)
        If record is locked, we just skip the update.
        It doesn't invalidate the cache since the update is not critical.

        :rtype: bool - if field has been incremented or not
    """
    if not record:
        return False

    assert record._fields[field].type == 'integer'

    cr = record._cr
    query = """
        UPDATE {table} SET {field} = {field} + 1 WHERE id IN (
            SELECT id from {table} WHERE id in %(ids)s FOR UPDATE SKIP LOCKED
        ) RETURNING id
    """.format(table=record._table, field=field)
    cr.execute(query, {'ids': tuple(record.ids)})

    return bool(cr.fetchone())
