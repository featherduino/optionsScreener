from . import websocket
from .websocket.defaults import MIN_PYTHON_MINOR, MIN_PYTHON_MAJOR
from colorama import init  # , Style, Fore, Back
# import sys
# import subprocess
# from time import sleep
# from copy import deepcopy
# from distutils import version
# import logging

init()  # Colorama

__version__ = '5.0.11'
# logger = logging.getLogger(__name__)
# logger.propagate = True

# try:
#     user_python_version = sys.version_info
#     print(user_python_version)
#     if not (user_python_version.major >= MIN_PYTHON_MAJOR and user_python_version.minor >= MIN_PYTHON_MINOR):
#         logger.warning(f"{Style.BRIGHT}{Fore.RED}\tIt is highly advised that you use Python {MIN_PYTHON_MAJOR}.{MIN_PYTHON_MINOR} or greater...\n"
#                        f"\tSome features may not work as intended on your version ({user_python_version.major}.{user_python_version.minor}.{user_python_version.micro})...{Style.RESET_ALL}")
#         logger.warning(f"\tPlease decide if you want to proceed with running as is or not...\n")
#         wrong_version_warning_input = input(f"\tReply with: {Back.CYAN}{Fore.BLACK}Y/N{Style.RESET_ALL} (Anything other than {Back.CYAN}{Fore.BLACK}Y{Style.RESET_ALL} will exit the code) : ")
#         if wrong_version_warning_input.upper()[0] != "Y":
#             exit()
# except Exception as e:
#     logger.error(f'{Style.BRIGHT}{Fore.RED}\tUnable to get the version of Python you are using...\n'
#                  f'\tPlease report this error to truedata...\n'
#                  f'\tAlong with the following information - {e}...{Style.RESET_ALL}')
# try:
#     op = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'truedata_ws=='], capture_output=True)
#     latest_version = max([version.StrictVersion(i.strip()) for i in str(op.stderr).split('from versions:')[1].split(')')[0].split(',')])
#     if latest_version > version.StrictVersion(__version__):
#         if version.StrictVersion(__version__) < version.StrictVersion('0.1.0'):
#             logger.warning(f'{Style.BRIGHT}{Fore.GREEN}Using DEVELOPER version (deVer-{__version__})...{Style.RESET_ALL}')
#         else:
#             logger.warning(f"{Style.BRIGHT}{Fore.GREEN}\tThere is a newer version of this library available ({latest_version}), while your version is {__version__}...\n"
#                            f"\tIt is highly advisable that you keep your libraries up-to-date... Please upgrade your library using-\n"
#                            f"\n\t\t python3.7 -m pip install --upgrade truedata_ws\n"
#                            f"\tWe also strongly recommend you read our release notes at the end of the README.md that is found at the end of PyPi page "
#                            f"(found at: https://pypi.org/project/truedata-ws/){Style.RESET_ALL}")
# except Exception as e:
#     # logger.error(f'{Style.BRIGHT}{Fore.RED}\tUnable to get latest version from PyPi...\n'
#     #              f'\tPlease report this error to truedata (https://github.com/kapilmar/truedata_ws/issues/new)...\n'
#     #              f'\tAlong with the following information - {e}...{Style.RESET_ALL}')
#     pass
