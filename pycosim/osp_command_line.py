# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_OSP_command_line_interface.ipynb.

# %% auto 0
__all__ = ['logger', 'ch', 'formatter', 'SimulationResult', 'SimulationError', 'ModelVariables', 'FMUModelDescription',
           'LoggingLevel', 'run_cli', 'run_single_fmu', 'deploy_output_config', 'deploy_scenario', 'clean_header',
           'run_cosimulation', 'deploy_files_for_cosimulation']

# %% ../nbs/00_OSP_command_line_interface.ipynb 4
import datetime as dt
import io
import logging
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from subprocess import Popen, PIPE
from sys import platform
from typing import NamedTuple, List, Dict, Union, Tuple, Any, cast
import time

import pandas
from pyOSPParser.scenario import OSPScenario, format_filename
from pyOSPParser.logging_configuration import OspLoggingConfiguration
from pyOSPParser.system_configuration import OspSystemStructure

# %% ../nbs/00_OSP_command_line_interface.ipynb 5
# Define logger
logger = logging.getLogger('__name__')
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

try:
    _MODULE_PATH = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _MODULE_PATH = os.path.dirname(os.path.abspath(""))

if platform.startswith("linux") or platform.startswith("darwin"):
    PATH_TO_COSIM = os.path.join(_MODULE_PATH, "..", "osp_cosim", "linux", "bin", "cosim")
else:
    PATH_TO_COSIM = os.path.join(_MODULE_PATH, "..", "osp_cosim", "win64", "bin", "cosim.exe")

@dataclass
class SimulationResult:
    """Simulation result"""
    result: Dict[str, pandas.DataFrame]
    log: str
    error: str = None


class SimulationError(Exception):
    """Exception for simulation error"""


class ModelVariables(NamedTuple):
    """ Representation of model variables from FMU's model description

    Attributes:
        parameters (List[Dict[str,str]], optional)
        inputs (List[Dict[str,str]], optional)
        outputs (List[Dict[str,str]], optional)
        others (List[Dict[str,str]], optional)
    """
    parameters: List[Dict[str, str]] = []
    inputs: List[Dict[str, str]] = []
    outputs: List[Dict[str, str]] = []
    others: List[Dict[str, str]] = []

    def get_parameters_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.parameters]

    def get_input_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.inputs]

    def get_output_names(self) -> List:
        """ Returns a list of the output names """
        return [variable['name'] for variable in self.outputs]

    def get_other_variable_names(self) -> List:
        """ Returns a list of the parameter names """
        return [variable['name'] for variable in self.others]


class FMUModelDescription(NamedTuple):
    """ Model description summary

    Model description summary used as a return type for get_model_description

    Attributes:
        name(str)
        uuid(str)
        model_variable (ModelVariables)
        description (str, optional)
        author (str, optional)
        version (str, optional)
    """
    name: str
    uuid: str
    model_variable: ModelVariables
    description: str = ''
    author: str = ''
    version: str = ''


class LoggingLevel(Enum):
    """Enum for logging level"""
    error = 40
    warning = 30
    info = 20
    debug = 10


def run_cli(args, log_output: bool = False) -> Tuple[str, str]:
    """Run the command line """
    output = b""
    log = b""
    try:
        with Popen(args=args, shell=True, stdout=PIPE, stderr=PIPE) as proc:
            if log_output:
                output = proc.stdout.read()
                log = proc.stderr.read()
    except OSError as exception:
        raise OSError(f'{output}, {log}, {exception}')

    # Catch errors

    return output.decode('utf-8'), log.decode('utf-8')


def run_single_fmu(
        path_to_fmu: str,
        initial_values: Dict[str, Union[float, bool]] = None,
        output_file_path: str = None,
        duration: float = None,
        step_size: float = None,
) -> SimulationResult:
    """Runs a single fmu simulation

    Args:
        path_to_fmu(str): file path to the target fmu
        initial_values(Dict[str, Union[float, bool]], optional): dictionary of initial values
        output_file_path(str, optional): file path for the output
        duration(float, optional): duration of simulation in seconds
        step_size(float, optional): duration
    Return:
        (tuple): tuple containing:
            result(pandas.DataFrame) simulation result
            log(str) simulation logging
    """
    fmu_name = os.path.splitext(os.path.basename(path_to_fmu))[0]
    delete_output = False
    if initial_values is None:
        initial_values = {}
    if output_file_path is None:
        # Delete output if the output file path is not given
        output_file_path = 'model-output.csv'
        delete_output = True
    mode = "run-single"

    assert os.path.isfile(PATH_TO_COSIM), f"The cosim CLI is not found: {PATH_TO_COSIM}"
    assert os.path.isfile(path_to_fmu), f"The fmu file is not found: {path_to_fmu}"

    # Create a list of initial values and set arguments for simulation
    args = [PATH_TO_COSIM, mode, path_to_fmu]
    args.extend(f'{key}={value}' for key, value in initial_values.items())
    args.append(f'--output-file={output_file_path}')
    if duration:
        args.append(f'-d{duration}')
    if step_size:
        args.append(f'-s{step_size}')

    #: Run the cosim to get the result in yaml format
    log, _ = run_cli(args)

    # Parse the output
    result_df = pandas.read_csv(output_file_path, index_col=False)
    result_df.index = result_df['Time'].values
    result_df.index.name = 'Time'
    result_df = result_df.drop(columns=['Time'])
    new_column_name = list(map(clean_header, result_df.columns))
    result_df.columns = new_column_name
    result = {fmu_name: result_df}
    if delete_output:
        os.remove(output_file_path)

    return SimulationResult(
        result=result,
        log=log
    )


def deploy_output_config(output_config: OspLoggingConfiguration, path: str):
    """Deploys a logging configiguration."""
    file_path = os.path.join(path, 'LogConfig.xml')

    xml_text = output_config.to_xml_str()

    with open(file_path, 'w+') as file:
        file.write(xml_text)


def deploy_scenario(scenario: OSPScenario, path: str):
    """Deploys a scenario"""
    dir_path = os.path.join(path, 'scenarios')
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)
    file_path = os.path.join(dir_path, scenario.get_file_name())

    with open(file_path, 'w+') as file:
        file.write(scenario.to_json())

    return file_path


def clean_header(header: str):
    """Clean header for simulation outputs"""
    if '[' in header:
        return header[0:header.rindex('[')-1]
    return header


def run_cosimulation(
        path_to_system_structure: str,
        output_file_path: str = None,
        scenario_name: str = None,
        duration: float = None,
        logging_level: LoggingLevel = LoggingLevel.warning,
        logging_stream: bool = False,
        time_out_s: int = 60,
) -> SimulationResult:
    """Runs a co-simulation. Should have run the deploy function first.

    Args:
        path_to_system_structure(str): The path to the system structure definition file/directory.
              If this is a file with .xml extension, or a directory that contains a file named
              OspSystemStructure.xml, it will be interpreted as a OSP system structure
              definition.
        output_file_path(str, optional): file path for the output
        scenario_name(str, optional), name for the scenario
        duration(float, optional): duration of simulation in seconds
        logging_level(LoggingLevel, optional): Sets the detail/severity level of diagnostic output.
            Valid arguments are 'error', 'warning', 'info', and 'debug'. Default is 'warning'.
        logging_stream(bool, optional): logging will be returned as a string if True value is given.
            Otherwise, logging will be only displayed.
        time_out_s(int, optional): time out in seconds
    Return:
        SimulationResult: object containing:
            result: simulation result
            log: simulation logging
            error: error from simulation
    """
    # Set loggers
    logger_local = logging.getLogger()
    if logging_stream:
        log_stream = io.StringIO()
        log_handler = logging.StreamHandler(log_stream)
        log_handler.setLevel(logging.INFO)
        logger_local.addHandler(log_handler)
    logger_local.setLevel(logging_level.value)

    # Set simulation parameters
    delete_output = False
    mode = "run"

    # Check if the cosim-cli exists and the system structure exists
    assert os.path.isfile(PATH_TO_COSIM), f'The cosim CLI is not found: {PATH_TO_COSIM}'
    assert os.path.isdir(path_to_system_structure), \
        f"The system structure directory is not found: {path_to_system_structure}"
    path_to_osp_sys_structure = os.path.join(path_to_system_structure, 'OspSystemStructure.xml')
    assert os.path.isfile(path_to_osp_sys_structure), \
        f'The system structure directory is not found: {path_to_system_structure}'
    args = [PATH_TO_COSIM, mode, path_to_system_structure]

    if output_file_path is None:
        output_file_path = path_to_system_structure
        delete_output = True
    else:
        assert os.path.isdir(output_file_path), \
            f"The directory for the output does not exist: {output_file_path}."
        logger_local.info(
            'Output csv files will be saved in the following directory: %s', output_file_path
        )
    args.append(f'--output-dir={output_file_path}')

    if scenario_name is not None:
        scenario_file_path = os.path.join(
            path_to_system_structure,
            "scenarios",
            f'{format_filename(scenario_name)}.json'
        )
        if not os.path.isfile(scenario_file_path):
            raise FileNotFoundError(f'The scenario file is not found: {scenario_file_path}')
        args.append(f'--scenario={scenario_file_path}')

    if duration:
        logger_local.info('Simulation will run until %f seconds.', duration)
        args.append(f'--duration={duration}')
    args.append(f'--log-level={logging_level.name}')

    # Run simulation
    logger_local.info('Running simulation.')
    simulation_start_time = time.time()
    _, log = run_cli(args)
    logger_local.info(log)
    error = [  # Find a error in the lines of logging and gather with a line break in between
        line_with_break for line in log.split('\n') if line.startswith('error')
        for line_with_break in [line, '\n']
    ]
    if len(error) > 1:
        error = error[:-1]
    error = ''.join(error)

    # construct result from csvs that are created within last 30 seconds
    output_files = []
    while len(output_files) == 0 and time.time() - simulation_start_time < time_out_s:
        output_files = [
            file_name for file_name in os.listdir(output_file_path) if file_name.endswith('csv')
        ]
        time.sleep(0.5)
    if len(output_files) == 0:
        error += f'No output files were created within the time out {time_out_s} seconds.\n'
    else:
        logger_local.info(
            "Simulation completed in %f seconds.", time.time() - simulation_start_time
        )
    ago = dt.datetime.now() - dt.timedelta(seconds=30)
    output_files = [
        file_name for file_name in output_files
        if dt.datetime.fromtimestamp(
            os.stat(os.path.join(output_file_path, file_name)).st_mtime
        ) > ago
    ]
    result = {}
    for file in output_files:
        simulator_name = file
        for _ in range(3):
            simulator_name = simulator_name[:simulator_name.rfind('_')]
        # Read the csv file for each simulator. The first column is usually the time.
        # There was a case that it caused a KeyError when passing "Time" as a key to the
        # index_col argument. Therefore, we set False to the index_col argument and
        # set the index value as Time after reading the csv file.
        result[simulator_name] = pandas.read_csv(
            os.path.join(output_file_path, file), index_col=False
        )
        result[simulator_name].index = result[simulator_name]["Time"].values
        result[simulator_name].index.name = "Time"
        result[simulator_name].drop(columns=["Time"], inplace=True)
        result[simulator_name].drop(["StepCount"], axis=1, inplace=True)
        new_column_name = list(map(clean_header, result[simulator_name].columns))
        result[simulator_name].columns = new_column_name
    if delete_output:
        for file_name in output_files:
            os.remove(os.path.join(output_file_path, file_name))

    # Get logging data
    if logging_stream:
        # noinspection PyUnboundLocalVariable
        logger_local.removeHandler(log_handler)
        log_handler.flush()
        # noinspection PyUnboundLocalVariable
        log_stream.flush()
        log = log_stream.getvalue()
    else:
        log = ''

    return SimulationResult(result=result, log=log, error=error)


def deploy_files_for_cosimulation(
        path_to_deploy: str,
        fmus: List[Any],
        system_structure: OspSystemStructure,
        rel_path_to_system_structure: str = '',
        logging_config: OspLoggingConfiguration = None,
        scenario: OSPScenario = None,
):
    """Deploy files for the simulation

    Returns:
        str: path to the system structure file
    """
    from pycosim.fmu import FMU
    # Update the state for the current path
    if not os.path.isdir(path_to_deploy):
        os.makedirs(path_to_deploy)
    logger.info("Deploying files to %s", path_to_deploy)
    # Create a fmu list from the components
    for fmu in fmus:
        fmu = cast(FMU, fmu)
        destination_file = os.path.join(path_to_deploy, os.path.basename(fmu.fmu_file))
        shutil.copyfile(fmu.fmu_file, destination_file)
        logger.info("Deployed %s", os.path.basename(fmu.fmu_file))
        # Deploy OspDescriptionFiles if there is
        if fmu.osp_model_description is not None:
            destination_file = os.path.join(
                path_to_deploy,
                f'{fmu.model_name}_OspModelDescription.xml'
            )
            with open(destination_file, 'wt') as osp_model_file:
                osp_model_file.write(fmu.osp_model_description.to_xml_str())
            logger.info("Deployed %s", os.path.basename(destination_file))

    # Check out with the path for the system structure file. If it doesn't exist
    # create the directory.
    path_to_sys_struct = os.path.join(path_to_deploy, rel_path_to_system_structure)
    if not os.path.isdir(path_to_sys_struct):
        os.mkdir(path_to_sys_struct)

    # Create a system structure file
    with open(
        file=os.path.join(path_to_sys_struct, 'OspSystemStructure.xml'),
        mode='wt',
        encoding='utf-8'
    ) as file:
        file.write(system_structure.to_xml_str())
    logger.info("System structure file is created.")

    # Create a logging config file
    if logging_config is not None:
        deploy_output_config(logging_config, path_to_sys_struct)
        logger.info('Deployed the logging configuration.')

    # Create a scenario file
    if scenario is not None:
        deploy_scenario(scenario, path_to_sys_struct)
        logger.info('Deployed the scenario.')

    return path_to_sys_struct
