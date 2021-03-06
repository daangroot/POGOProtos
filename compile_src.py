#!/usr/bin/env python
# This Python file uses the following encoding: utf-8

import argparse
import errno
import os
import re
import shutil
import sys
from subprocess import call


def abslistdir(path):
    return " ".join(map((lambda f: os.path.join(os.path.abspath(path), f)), os.listdir(path)))


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def finish_compile(out_path, lang):
    if lang == 'python':
        pogo_protos_path = os.path.join(out_path, "pogoprotos")

        for root, dirnames, filenames in os.walk(pogo_protos_path):
            init_path = os.path.join(root, '__init__.py')

            with open(init_path, 'w') as init_file:
                if pogo_protos_path is root:
                    init_file.write(
                        "'Generated'; import os; import sys; sys.path.append(os.path.dirname(os.path.realpath(__file__)))")


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def convert_to_go_package(pkg):
    pkg = pkg.replace("POGOProtos.", "")
    pkg = pkg.replace(".", "_").lower()
    if pkg == "map":
        pkg = "maps"

    return pkg


def to_lower_case(string):
    string = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', string)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', string).lower()


def read_proto(path):
    package = None
    imports = []
    content = []
    with open(path, 'r') as file:
        is_header = True
        for line in file.readlines():
            line = line.rstrip()
            if is_header:
                if line.startswith('package'):
                    match = re.match(r'package (\w+(?:\.\w+)*);', line)
                    package = match.group(1)
                elif line.startswith('import'):
                    match = re.match(
                        r'import (public )?"(\w+(?:\/\w+)*)\.proto";', line)
                    import_path = match.group(2)
                    import_is_public = False if match.group(
                        1) is None else True
                    imports.append((import_path, import_is_public))
                elif line.startswith('message') or line.startswith('enum'):
                    is_header = False
            if not is_header and line:
                content.append(line)
        content.append('')
    return (package, imports, content)


def read_protos(path):
    protos = dict()
    for folder_path, _, file_names in os.walk(path):
        proto_folder = dict()
        for file_name in file_names:
            if file_name.endswith('.proto'):
                file_path = os.path.join(folder_path, file_name)
                key, _ = os.path.splitext(file_name)
                proto_folder[key] = read_proto(file_path)
        if proto_folder:
            key = '/'.join(
                os.path.normpath(
                    os.path.relpath(
                        folder_path,
                        path)).split(
                    os.sep))
            protos[key] = proto_folder
    return protos


def write_proto(path, name, proto):
    package, imports, content = proto

    if not os.path.exists(path):
        os.makedirs(path)

    proto_file = os.path.abspath(os.path.join(path, name + '.proto'))

    with open(proto_file, 'w') as file:
        file.write('syntax = "proto3";\n\n')
        file.write('package ')
        file.write(package)
        file.write(';\n\n')

        options = False

        if args.language == 'cpp' and args.cc_enable_arenas:
            options = True
            file.write('option cc_enable_arenas = true;\n')

        if args.language == 'java' or args.language == 'javanano' and args.java_multiple_files:
            options = True
            file.write('option java_multiple_files = true;\n')

        if args.language == 'objc':
            options = True
            file.write('option objc_class_prefix = "";\n')

        if args.language == 'go':
            options = True
            go_package = package.split('.')[-1]
            file.write('option go_package = "')
            file.write(go_package)
            file.write('";\n')

        if options:
            file.write('\n')

        for import_path, import_is_public in imports:
            file.write('import "')
            if import_is_public:
                file.write('public ')
            file.write(import_path)
            file.write('.proto";\n')

        if imports:
            file.write('\n')

        for line in content:
            file.write(line)
            file.write('\n')

    return proto_file


def write_protos(path, protos):
    proto_files = []
    for proto_path in protos:
        proto_files_folder = []
        proto_folder = protos[proto_path]
        proto_path = os.path.join(*proto_path.split('/'))
        for proto_file_name in proto_folder:
            proto = proto_folder[proto_file_name]
            proto_files_folder.append(
                write_proto(
                    os.path.join(
                        path,
                        proto_path),
                    proto_file_name,
                    proto))
        proto_files.append(proto_files_folder)
    return proto_files


def format_protos(
        protos,
        path,
        namespace,
        path_lower,
        file_lower,
        package_lower):
    packages = []
    for proto_path in protos:
        proto_folder = protos[proto_path]
        for proto_file_name in proto_folder:
            package, _, _ = proto_folder[proto_file_name]
            packages.append('.'.join(package.split('.')[1:]))
    new_protos = dict()
    for proto_path in protos:
        proto_folder = protos[proto_path]
        new_proto_folder = dict()
        new_proto_path = path + '/' + '/'.join(proto_path.split('/')[1:])
        if path_lower:
            new_proto_path = new_proto_path.lower()
        for proto_file_name in proto_folder:
            new_proto_file_name = to_lower_case(
                proto_file_name) if file_lower else proto_file_name
            package, imports, content = proto_folder[proto_file_name]
            new_package = namespace + '.' + '.'.join(package.split('.')[1:])
            if package_lower:
                new_package = new_package.lower()
            new_imports = []
            for import_path, import_is_public in imports:
                import_path_split = import_path.split('/')
                import_path_path = '/'.join(import_path_split[:-1])
                if import_path.startswith('POGOProtos/'):
                    if import_path_split[1:-1]:
                        import_path_path = path + '/' + \
                                           '/'.join(import_path_split[1:-1])
                    else:
                        import_path_path = path
                if path_lower:
                    import_path_path = import_path_path.lower()
                import_path_file = import_path_split[-1]
                if file_lower:
                    import_path_file = to_lower_case(import_path_file)
                import_path = import_path_path + '/' + import_path_file
                new_imports.append((import_path, import_is_public))
            new_content = []

            def sub(match):
                type = match.group(1)
                found_package = ''
                for package in packages:
                    if type.startswith(
                            package + '.') and len(package) > len(found_package):
                        found_package = package
                type = type[len(found_package):]
                found_package = namespace + '.' + found_package
                if package_lower:
                    found_package = found_package.lower()
                return found_package + type

            for line in content:
                new_content.append(
                    re.sub(
                        '\.?POGOProtos.(\w+(?:\.\w+)*)',
                        sub,
                        line))
            new_proto_folder[new_proto_file_name] = (
                new_package, new_imports, new_content)
        new_protos[new_proto_path] = new_proto_folder
    return new_protos


parser = argparse.ArgumentParser()
parser.add_argument(
    'language',
    choices=[
        'objc',
        'php',
        'cpp',
        'csharp',
        'python',
        'ruby',
        'java',
        'javanano',
        'js',
        'go',
        'rust',
        'swift',
        'lua',
        'dart'],
    help='language to pass to protoc')
parser.add_argument(
    '-p', '--protoc_path',
    default='protoc',
    help='path to protoc')
parser.add_argument(
    '-o', '--out_path',
    default='out',
    help='output path for protoc')
parser.add_argument(
    '--cc_enable_arenas',
    action='store_true',
    help='enable C++ arena allocation')
parser.add_argument(
    '--generate_desc',
    action='store_true',
    help='generate a .desc file')
parser.add_argument(
    '--include_imports',
    action='store_true',
    help='include imports in .desc file')
parser.add_argument(
    '--include_source_info',
    action='store_true',
    help='do not strip source code info from .desc file')
parser.add_argument(
    '--keep_proto_files',
    action='store_true',
    help='do not remove .proto files after compiling')
parser.add_argument(
    '--java_multiple_files',
    action='store_true',
    help='Write each message to a separate .java file.')
args = parser.parse_args()

protoc_path = args.protoc_path
src_path = os.path.join(os.path.dirname(__file__), 'src')
out_path = os.path.abspath(args.out_path)

if os.path.exists(out_path):
    shutil.rmtree(out_path)

if not os.path.exists(out_path):
    os.makedirs(out_path)

namespace = 'POGOProtos'
path = 'POGOProtos'
path_lower = False
file_lower = False
package_lower = False

if args.language == 'go':
    namespace = 'pogoprotos'
    path = 'pogoprotos'
    path_lower = True
    file_lower = True
    package_lower = True
elif args.language == 'python':
    namespace = 'pogoprotos'
    path = 'pogoprotos'
    path_lower = True
    file_lower = True
    package_lower = True
elif args.language == 'js':
    namespace = 'pogoprotos'
    path = 'pogoprotos'
    path_lower = True
    file_lower = True
    package_lower = True
elif args.language == 'ruby':
    namespace = 'POGOProtos'
    path = 'pogoprotos'
    path_lower = True
    file_lower = True
    package_lower = False
elif args.language == 'rust':
    namespace = 'pogoprotos'
    path = 'pogoprotos'
    path_lower = True
    file_lower = True
    package_lower = True

protos = read_protos(src_path)

protos = format_protos(
    protos,
    path,
    namespace,
    path_lower,
    file_lower,
    package_lower)

if args.language == 'go':
    new_protos = dict()
    for proto_path in protos:
        proto_folder = protos[proto_path]
        new_proto_path = re.sub('/map', r'/maps', proto_path)
        new_proto_folder = dict()
        for proto_file_name in proto_folder:
            package, imports, content = proto_folder[proto_file_name]
            new_package = re.sub('\.map', r'.maps', package)
            new_imports = []
            for import_path, import_is_public in imports:
                new_imports.append(
                    (re.sub(
                        '/map/',
                        r'/maps/',
                        import_path),
                     import_is_public))
            new_content = []
            for line in content:
                new_content.append(re.sub('\.map\.', r'.maps.', line))
            new_proto_folder[proto_file_name] = (
                new_package, new_imports, new_content)
        new_protos[new_proto_path] = new_proto_folder
    protos = new_protos

proto_folders = write_protos(out_path, protos)
proto_files = sum(proto_folders, [])

commands = []

if args.generate_desc:
    desc_path = os.path.join(out_path, *path.split('/')) + '.desc'
    desc_arguments = []
    if args.include_imports:
        desc_arguments.append('--include_imports')
    if args.include_source_info:
        desc_arguments.append('--include_source_info')

    commands.append(
        """"{0}" --proto_path="{1}" --descriptor_set_out="{2}" {3} {4}""".format(
            args.protoc_path,
            out_path,
            desc_path,
            ' '.join(desc_arguments),
            '"' +
            '" "'.join(proto_files) +
            '"'))

arguments = ''
options = ''
all_at_once = True

if args.language == 'js':
    options = 'import_style=commonjs,binary'
elif args.language == 'csharp':
    arguments = '--csharp_opt=file_extension=.g.cs --csharp_opt=base_namespace'
elif args.language == 'dart':
    arguments = '--plugin "pub run protoc_plugin"'
elif args.language == 'lua':
    arguments = '--plugin=protoc-gen-lua="../ProtoGenLua/plugin/build.bat"'
elif args.language == 'go':
    options = 'plugins=grpc'
    all_at_once = False
elif args.language == 'swift':
    arguments = '--swift_opt=Visibility=Public'

if all_at_once:
    proto_folders = [proto_files]

for proto_files in proto_folders:
    for proto_file in proto_files:
        commands.append(
            """"{0}" --proto_path="{1}" --{2}_out={3}:"{4}" {5} {6}""".format(
                args.protoc_path,
                out_path,
                args.language,
                options,
                out_path,
                arguments,
                '"' + proto_file + '"'))

for command in commands:
    call(command, shell=True)

if args.language == 'python':
    finish_compile(out_path, args.language)

elif args.language == 'ruby':
    for path in protos:
        with open(os.path.join(out_path, *path.split('/')) + '.rb', 'w') as file:
            for name in protos[path]:
                file.write('require "' + path + '/' + name + '"\n')

# Remove all .proto files
if not args.keep_proto_files:
    for folder_path, _, file_names in os.walk(out_path):
        for file_name in file_names:
            if file_name.endswith(".proto"):
                os.unlink(os.path.join(folder_path, file_name))
