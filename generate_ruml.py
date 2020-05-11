import ast
import importlib
import logging
import os
import pyclbr
import sys
from collections import defaultdict
from trace import Trace

import pandas as pd

from dependency_collector import ModuleUseCollector
from generate_hierarchy import GenerateHierarchy
from generate_sequence_diagram import GenerateSequenceDiagram
from plot_uml_in_excel import WriteInExcel

foo = None

logging.basicConfig(level=logging.DEBUG)


class GRUML:

    def __init__(self, test=False):
        self.source_code_path = []
        self.source_code_modules = []
        self.driver_path = None
        self.driver_name = None
        self.test = test
        self.use_case = True
        self.class_object_mapping = defaultdict(dict)
        global foo
        self.foo = foo

    def get_source_code_path_and_modules(self, source_code_path):
        """input source code that is to be studied and compute all
        modules inside it.
        """
        self.source_code_path = [source_code_path]
        cwd = os.getcwd()
        # os.chdir(self.source_code_path)
        root_dir = os.path.basename(os.path.normpath(self.source_code_path[0]))
        for (dirpath, _, filenames) in os.walk(self.source_code_path[0]):
            for file in filenames:
                if file.endswith(".py"):
                    rel_dir = os.path.relpath(
                        dirpath, self.source_code_path[0])
                    file = os.path.join(
                        rel_dir, file) if rel_dir != '.' else file
                    file = file.split(".py")[0]
                    if file.startswith(root_dir):
                        file = file.split(root_dir)[-1]
                    self.source_code_modules += [file.replace('/', '.')]
        os.chdir(cwd)

    def get_driver_path_and_driver_name(self, use_case, driver_name, driver_path, driver_function):
        """ask for driver path and driver module's  name.

        Returns:
            str, str, str, str -- returns use case, driver path, driver name, driver function.
        """
        if not use_case:
            self.use_case = False
            return
        self.use_case = use_case
        self.driver_name = driver_name
        self.driver_path = os.path.join(self.source_code_path[0], driver_path)
        self.driver_function = driver_function

    def generate_dependency_data(self):
        """generate dependency (inheritance and non-inheritance) data.
        """
        agg_data = defaultdict(list)
        # dictionary to store all files: classes mapping. If a .py file has three classes, their name, start and end line will be stored here.
        files = {}
        class_index = defaultdict(lambda: defaultdict(int))
        # to check if a class has already been covered due to some import in another file.
        self.classes_covered = defaultdict(lambda: defaultdict(int))
        for source_code_module in self.source_code_modules:
            counter = 0
            source_code_module, source_code_path = os.path.basename(source_code_module), [os.path.join(
                self.source_code_path[0], os.path.dirname(source_code_module))]
            # source_code_data = pyclbr.readmodule(
            #     source_code_module, path=source_code_path)
            source_code_data = pyclbr.readmodule_ex(
                source_code_module, path=source_code_path)
            generate_hierarchy = GenerateHierarchy()
            for name, class_data in source_code_data.items():
                # don't cover classes that are not in the source code modules
                if class_data.module not in self.source_code_modules:
                    continue
                self.class_object_mapping[class_data.module]['{}'.format(
                    class_data.name)] = class_data
                methods = []
                parents = []
                if isinstance(class_data, pyclbr.Class):
                    methods = generate_hierarchy.show_methods(name, class_data)
                    parents = generate_hierarchy.show_super_classes(
                        name, class_data, self)
                file_ = class_data.file
                start_line = class_data.lineno,
                end_line = class_data.end_lineno
                module = class_data.module
                if module in self.classes_covered:
                    if self.classes_covered[module].get(name):
                        continue
                agg_data[module].append(
                    {
                        "Class": name,
                        "Methods": methods,
                        "Parents": parents,
                        "File": file_,
                        "Start Line": start_line,
                        "End Line": end_line,
                        "Dependents": []
                    }
                )
                if files.get(class_data.file, None):
                    files[class_data.file].append(
                        {'class': name, 'start_line': class_data.lineno, 'end_line': class_data.end_lineno})
                else:
                    files[class_data.file] = [
                        {'class': name, 'start_line': class_data.lineno, 'end_line': class_data.end_lineno}]
                class_index[module][name] = len(agg_data[module])-1
                counter += 1
                self.classes_covered[module][name] = 1
        logging.debug(' ---------------------------------- ')
        for _ in range(20):
            print('\n')
        # extract inter-file dependencies i.e. if a file's classes have been used in other files. Files being modules here.
        for file_ in files.keys():
            module = file_.split('/')[-1].split('.py')[0]
            for j in files.keys():
                try:
                    source = open(j).read()
                    collector = ModuleUseCollector(module)
                    collector.visit(ast.parse(source))
                    for use_ in collector.used_at:
                        _class = use_[0].split(".")[-1]
                        alias = use_[1]
                        line_no = use_[2]
                        for class_ in files[j]:
                            logging.debug('Checking for class {} in file {} and _class is {}'.format(
                                class_, files[j], _class))
                            if ((class_['start_line'] < line_no) and (class_['end_line'] > line_no)):
                                dependent_module = j.split(
                                    '/')[-1].split('.py')[0]
                                agg_data[module][class_index[module][_class]]['Dependents'].append(
                                    {'module': dependent_module, 'class': class_['class']})
                except AttributeError:
                    pass
                except KeyError as key_error:
                    logging.debug(
                        'Class {} was not found in agg_data but was brought up while checking non-inheritance dependencies, generating error: {}'.format(
                            _class, key_error
                        )
                    )
        # extract intra-file dependencies
        for file_ in files.keys():
            with open(file_) as f:
                data = f.read()
                module = ast.parse(data)
                classes = [obj for obj in module.body if isinstance(
                    obj, ast.ClassDef)]
                class_names = [obj.name for obj in classes]
                dependencies = {name: [] for name in class_names}
                for class_ in classes:
                    for node in ast.walk(class_):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name):
                                if node.func.id != class_.name and node.func.id in class_names:
                                    dependencies[class_.name].append(
                                        node.func.id)
            module_name = file_.split('/')[-1].split('.py')[0]
            for class_name, dependency in dependencies.items():
                for dependee_class in dependency:
                    agg_data[module_name][class_index[module_name][dependee_class]]['Dependents'].append(
                        {'module': module_name, 'class': class_name})

        self.skip_cols = 0
        parents_or_dependees_set = set()
        for module in agg_data.keys():
            for class_ in agg_data[module]:
                if class_['Dependents']:
                    parents_or_dependees_set.add(
                        '{}.{}'.format(module, class_['Class']))
                if class_['Parents']:
                    for parent in class_['Parents']:
                        parents_or_dependees_set.add('{}.{}'.format(
                            parent['parent_module'], parent['parent_class']))
        self.skip_cols = len(parents_or_dependees_set)
        # The whole data is now collected and we need to form the dataframe of it:
        self.write_in_excel = WriteInExcel(file_name='Dependency_2.xlsx')
        self.df = self.write_in_excel.create_pandas_dataframe(
            agg_data, self.skip_cols)
        logging.debug('Dataframe is: \n')
        logging.debug(self.df)
        self.write_in_excel.write_df_to_excel(
            self.df, 'sheet_one', self.skip_cols, self.classes_covered)

    def generate_sequential_function_calls(self):
        """generate sequential function calls
        for tracing source code and plotting sequence diagram.
        """
        # generating sequence diagram for a use-case
        _ = GenerateSequenceDiagram(
            self.driver_path, self.driver_name, self.source_code_path[0])
        spec = importlib.util.spec_from_file_location(
            self.driver_name, self.driver_path)
        global foo
        foo = self.foo
        foo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(foo)
        tracer = Trace(countfuncs=1, countcallers=1, timing=1)
        tracer.run('foo.{}()'.format(self.driver_function))
        results = tracer.results()
        caller_functions = results.callers
        function_sequence = []  # consists of all functions called in sequence
        for caller, callee in caller_functions:
            _, caller_module, caller_function = caller
            _, callee_module, callee_function = callee
            if caller_module not in self.source_code_modules or callee_module not in self.source_code_modules:
                logging.debug(
                    "Following modules are not in source code and thus to be ignored:")
                logging.debug(caller_module)
                continue
            function_sequence.append(
                [(caller_module, caller_function), (callee_module, callee_function)])
        logging.debug("Function sequence is: ")
        for sequence in function_sequence:
            logging.debug(sequence)
        self.df = self.write_in_excel.integrate_sequence_diagram_in_df(
            self.df, function_sequence, self.use_case, self.driver_function, self.skip_cols)
        self.write_in_excel.write_df_to_excel(
            self.df, 'sheet_one', self.skip_cols, self.classes_covered, self.use_case)


def gruml(source_code_path, **kwargs):
    """driver function of GRUML.
    """
    gruml = GRUML()
    print('Generating RUML for source code at: {}'.format(source_code_path))
    gruml.get_source_code_path_and_modules(source_code_path)
    gruml.get_driver_path_and_driver_name(
        kwargs.get('use_case', None),
        kwargs.get('driver_name', None),
        kwargs.get('driver_path', None),
        kwargs.get('driver_function', None),
    )
    gruml.generate_dependency_data()
    if gruml.use_case:
        gruml.generate_sequential_function_calls()


kwargs = {
    'use_case':'test_cli',
    'driver_name':'driver',
    'driver_path': 'driver.py',
    'driver_function': 'main_2'
}

gruml('/tmp/python3-class-inheritance-dependency-example/python3-class-inheritance-dependency-example', **kwargs)