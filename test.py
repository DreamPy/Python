import os

import optparse
import pyang
from xml.etree import ElementTree
import utils


def camel_to_kernel(name):
    if '_' in name:
        return name
    new_name = name[0]
    for c in name[1:]:
        if c.isupper():
            new_name += '_' + c
        else:
            new_name += c
    return new_name


class Meta(type):
    def __init__(cls, *args, **kwargs):
        def __setattr__(self, key, value):
            raise AttributeError('can\'t set attribute', key, value)

        cls.__class__.__setattr__ = __setattr__
        cls.__class__.__str__ = lambda self: camel_to_kernel(self.__name__)
        super(Meta, cls).__init__(cls, args, kwargs)

    def __new__(mcs, name, bases, attrs):
        for key, value in attrs.items():
            if isinstance(value, type) and not isinstance(value, Meta):
                attrs[key] = Meta(key, bases=(ReadOnly,), attrs=dict(value.__dict__))
        return super(Meta, mcs).__new__(mcs, name, bases, attrs)


class ReadOnly(metaclass=Meta):
    def __new__(cls, *args, **kwargs):
        raise TypeError('Can\'t instantiate class')


class Levels(ReadOnly):
    class Warning:
        pass

    class Error:
        pass

    class Info:
        pass


sample_callback = None


class CheckInfo(ReadOnly):
    class ListCheck:
        error_code = 0x1234
        node_name = 'list|typedef'
        notice = '%s %s %s'

        @staticmethod
        def callback(stmt):
            return sample_callback(stmt)

        level = Levels.Warning

    class ListCheckName:
        error_code = 0x1234
        node_name = 'list|leaf'
        notice = '%s %s %s'

        @staticmethod
        def callback(stmt):
            return sample_callback_2(stmt)

        level = Levels.Warning

    class ListCheck1:
        error_code = 0x1234
        node_name = 'list'
        notice = ''

        @staticmethod
        def callback(stmt):
            return sample_callback(stmt)

        level = Levels.Warning

    class ListCheckName2:
        error_code = 0x1234
        node_name = 'list'
        notice = ''
        level = Levels.Warning

        @staticmethod
        def callback(stmt):
            return sample_callback(stmt)

    @classmethod
    def check_unique(cls):
        pass


class Position:
    def __init__(self, ref, line, module_name):
        self.line = line
        self.ref = os.path.abspath(ref)
        self.module_name = module_name

    def __eq__(self, other):
        return self.line == other.line and self.ref == other.ref and self.module_name == other.module_name

    def __gt__(self, other):
        return True if (self.line - other.line) > 0 else False

    def __ge__(self, other):
        return self > other or self.line == other.line

    def __hash__(self):
        return hash((self.line, self.ref, self.module_name))

    def __str__(self):
        return self.ref + ':' + str(self.line)


class Record:
    def __init__(self, pos, check_item, extra):
        self.pos = pos
        self.check_item = check_item
        self.extra = extra

    def __eq__(self, other):
        return self.pos == other.pos and self.check_item == other.check_item and self.extra == other.extra

    def __ge__(self, other):
        return self.pos >= other.pos

    def __gt__(self, other):
        return self.pos > other.pos

    def __hash__(self):
        return hash((self.pos, str(self.check_item), self.extra))

    def __str__(self):
        return ' <-|-> '.join(
            [str(self.pos), str(self.check_item), str(self.check_item.level), self.pos.module_name, str(self.extra)])


class Records(set):
    def to_xml(self):
        rs = self.to_dict()
        report = ElementTree.Element('report')
        attrs = {
            'pos': None,
            'name': None,
            'detail': None,
            'level': None
        }
        total = {
            'Warning': 0,
            'Error': 0,
            'Info': 0
        }
        for (file, module_name), records in rs.items():
            module = ElementTree.Element('module', {'name': module_name, 'file': file})

            for record in sorted(records):
                attrs['pos'] = str(record.pos)
                attrs['name'] = str(record.check_item).upper()
                level = str(record.check_item.level)
                attrs['level'] = level
                total[level] += 1
                attrs['detail'] = record.check_item.notice % record.extra
                ElementTree.SubElement(module, 'item', attrs)
            #     reset attrs
                for k, v in attrs.items():
                    attrs[k] = None
            for key, value in total.items():
                module.set(key, str(value))
                total[key] = 0
            report.append(module)
        utils.pretty_xml(report, indent=' ' * 4, newline='\n')

        return report

    def to_json(self):
        pass

    def to_dict(self, how_to_choose_key=None):
        results = {}

        def _choose_module_name_as_key(record_):
            return record_.pos.ref, record_.pos.module_name

        if how_to_choose_key is None:
            how_to_choose_key = _choose_module_name_as_key
        for record in self:
            results.setdefault(how_to_choose_key(record), Records()).add(record)

        return results


def __str__(self):
    return '\n'.join(map(str, self))


user_selected = [
    CheckInfo.ListCheck,
    CheckInfo.ListCheckName
]


def create_maps_from_user_selected(user_selected_):
    maps_ = {}
    for selected in user_selected_:
        for node in selected.node_name.split('|'):
            maps_.setdefault(node, set()).add(selected.callback)
    return maps_


def iter_(stmt):
    yield stmt
    for s in stmt.substmts:
        yield s
        iter_(s)


def activate(keyword, maps):
    maps.setdefault(keyword, set())
    for callback in maps[keyword]:
        yield callback


class Tree:
    def __init__(self, keyword, ref, line, module_name):
        self.keyword = keyword
        self.ref = ref
        self.line = line
        self.module_name = module_name


def sample_callback(stmt):
    return Record(Position(stmt.pos.ref, stmt.pos.line, stmt.pos.top.arg), CheckInfo.ListCheckName,
                  ('hello world', stmt.arg, stmt.keyword))


def sample_callback_2(stmt):
    return Record(Position(stmt.ref, 21, stmt.module_name), CheckInfo.ListCheck, ('hello world! i am lx',))


class Test(CheckInfo):
    class LeafCheck:
        pass


def run():
    # deal opt

    usage = """%prog [options] [<filename>...]

    Validates the YANG module in <filename> (or stdin), and all its dependencies."""
    optlist = [
        # use capitalized versions of std options help and version
        optparse.make_option("-h", "--help",
                             action="help",
                             help="Show this help message and exit"),
        optparse.make_option("-v", "--version",
                             action="version",
                             help="Show version number and exit"),
        optparse.make_option("-V", "--verbose",
                             action="store_true"),
        optparse.make_option("-p", "--path",
                             dest="path",
                             default=[],
                             action="append",
                             help=os.pathsep + "-separated search path for yin"
                                               " and yang modules"),
        optparse.make_option("--no-path-recurse",
                             dest="no_path_recurse",
                             action="store_true",
                             help="Do not recurse into directories in the \
                               yang path."),
    ]

    optparser = optparse.OptionParser(usage, add_help_option=False)
    optparser.version = '%prog ' + pyang.__version__
    optparser.add_options(optlist)
    (o, args) = optparser.parse_args()

    # get yang tree
    path = os.pathsep.join(o.path)
    repos = pyang.FileRepository(path, use_env=False, no_path_recurse=o.no_path_recurse,
                                 verbose=o.verbose)
    ctx = pyang.Context(repos)

    for module_name in ctx.revs:
        ctx.add_parsed_module(ctx.read_module(module_name))

    # iterate
    records = Records()
    # deal grammar error
    codes = pyang.error.error_codes
    # levels = ['critical_error', 'major_error', 'minor_error', 'warning']
    rename_levels = ['Error'] * 3 + ['Warning']

    for pos, type_, key in ctx.errors:
        level, template = codes[type_]

        records.add(Record(Position(pos.ref, pos.line, pos.top.arg),
                           Meta(name=type_, bases=(ReadOnly,),
                                attrs={
                                    'level': rename_levels[level], 'notice': template.replace('"', "'")
                                }),
                           (key,)
                           )
                    )
    # deal self define error
    maps = create_maps_from_user_selected(user_selected)
    for module in ctx.modules.values():
        for stmt in iter_(module):
            for callback in activate(stmt.keyword, maps):
                record = callback(stmt)
                records.add(record)

    print(ElementTree.tostring(records.to_xml()).decode('utf-8'))


if __name__ == '__main__':
    run()
    # report = ElementTree.Element('report')
    # report.append(report.makeelement('?xml', {'hello': 'hello world'}))
    # print(ElementTree.tostring(report,True))
    print(CheckInfo, [3] * 3)
