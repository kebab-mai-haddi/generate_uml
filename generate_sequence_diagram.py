from trace import Trace
import importlib
# from driver import main_2
import os


class GenerateSequenceDiagram:
    def __init__(self, driver_module):
        # self.driver_module = __import__(driver_module)
        print('inside init of gen seq diag, dir is: {}'.format(os.getcwd()))
        self.driver_module = importlib.import_module(driver_module)

    def get_called_functions(self, driver_function):
        self.driver_function = getattr(self.driver_module, driver_function)
        self.driver_function()
        # print(dir(self.driver_function))
        # print(self.driver_function.__name__)
        tracer = Trace(countfuncs=1)
        tracer.run('{}()'.format(self.driver_function.__name__))
        results = tracer.results()
        called_functions = results.calledfuncs
        return called_functions


# ob = GenerateSequenceDiagram('driver')
# print(ob.get_called_functions('main_2'))
