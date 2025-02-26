"""
Data Analysis and Simulation Pipeline.

A data analysis pipeline is completely specified by a YAML file that specifies
both what tasks are to be run and the parameters that go to those tasks.
Included in this package are base classes for simplifying the construction of
data analysis tasks, as well as the pipeline manager which executes them.

Pipelines are most easily executed using the script in `caput_pipeline.py`,
which ships with :mod:`caput`.

Flow control classes
====================
- :py:class:`Manager`
- :py:class:`PipelineRuntimeError`
- :py:class:`PipelineStopIteration`

Task base classes
=================
- :py:class:`TaskBase`
- :py:class:`SingleBase`
- :py:class:`IterBase`
- :py:class:`H5IOMixin`
- :py:class:`BasicContMixin`
- :py:class:`SingleH5Base`
- :py:class:`IterH5Base`



Examples
========

Basic Tasks
-----------

A pipeline task is a subclass of :class:`TaskBase` intended to perform some small,
modular piece analysis. The developer of the task must specify what input
parameters the task expects as well as code to perform the actual processing
for the task.

Input parameters are specified by adding class attributes whose values are
instances of :class:`config.Property`. For instance a task definition might begin
with

>>> class SpamTask(TaskBase):
...     eggs = config.Property(proptype=str)

This defines a new task named :class:`SpamTask` with a parameter named *eggs*, whose
type is a string.  The class attribute :attr:`SpamTask.eggs` will replaced with an
instance attribute when an instance of the task is initialized, with it's value
read from the pipeline configuration YAML file (see next section).

The actual work for the task is specified by over-ridding any of the
:meth:`~TaskBase.setup`, :meth:`~TaskBase.next` or
:meth:`~TaskBase.finish` methods (:meth:`~TaskBase.__init__` may also be
implemented`).  These are executed in order, with :meth:`~TaskBask.next`
possibly being executed many times.  Iteration of :meth:`next` is halted by
raising a :exc:`PipelineStopIteration`.  Here is a example of a somewhat
trivial but fully implemented task:

>>> class PrintEggs(TaskBase):
...
...     eggs = config.Property(proptype=list)
...
...     def __init__(self):
...         super().__init__()
...         self.i = 0
...
...     def setup(self):
...         print("Setting up PrintEggs.")
...
...     def next(self):
...         if self.i >= len(self.eggs):
...             raise PipelineStopIteration()
...         print("Spam and %s eggs." % self.eggs[self.i])
...         self.i += 1
...
...     def finish(self):
...         print("Finished PrintEggs.")

Any return value of these three pipeline methods can be handled by the pipeline
and provided to subsequent tasks. The methods :meth:`setup` and :meth:`next`
may accept (positional only) arguments which will be received as the outputs of
early tasks in a pipeline chain. The following is an example of a pair of tasks
that are designed to operate in this manner.

>>> class GetEggs(TaskBase):
...
...     eggs = config.Property(proptype=list)
...
...     def __init__(self):
...         super().__init__()
...         self.i = 0
...
...     def setup(self):
...         print("Setting up GetEggs.")
...
...     def next(self):
...         if self.i >= len(self.eggs):
...             raise PipelineStopIteration()
...         egg = self.eggs[self.i]
...         self.i += 1
...         return egg
...
...     def finish(self):
...         print("Finished GetEggs.")

>>> class CookEggs(TaskBase):
...
...     style = config.Property(proptype=str)
...
...     def setup(self):
...         print("Setting up CookEggs.")
...
...     def next(self, egg):
...         print("Cooking %s %s eggs." % (self.style, egg))
...
...     def finish(self):
...         print("Finished CookEggs.")

Note that :meth:`CookEggs.next` never raises a :exc:`PipelineStopIteration`.
This is because there is no way for the task to internally know how long to
iterate.  :meth:`next` will continue to be called as long as there are inputs
for :meth:`next` and will stop iterating when there are none.

Pipeline Configuration
----------------------

To actually run a task or series of tasks, a YAML pipeline configuration is
required.  The pipeline configuration has two main functions: to specify the
the pipeline (which tasks are run, in which order and how to handle the inputs and
outputs of tasks) and to provide parameters to each individual task.  Here is
an example of a pipeline configuration:

>>> spam_config = '''
... pipeline :
...     tasks:
...         -   type:   PrintEggs
...             params: eggs_params
...
...         -   type:   GetEggs
...             params: eggs_params
...             out:    egg
...
...         -   type:   CookEggs
...             params: cook_params
...             in:     egg
...
... eggs_params:
...     eggs: ['green', 'duck', 'ostrich']
...
... cook_params:
...     style: 'fried'
...
... '''

Here the 'pipeline' section contains parameters that pertain to the pipeline as
a whole.  The most important parameter is *tasks*, a list of tasks to be
executed.  Each entry in this list may contain the following keys:

type
    (required) The name of the class relative to the global
    name space. Any required imports will be performed dynamically.  Any
    classes that are not importable (defined interactively) need to be
    registered in the dictionary ``pipeline.local_tasks``.
params
    (required) Key or list of keys referring to sections of the pipeline
    configuration holding parameters for the task.
out
    A 'pipeline product key' or list of keys that label any return values from
    :meth:`setup`, :meth:`next` or :meth:`finish`.
requires
    A 'pipeline product key' or list of keys representing values to be passed
    as arguments to :meth:`setup`.
in
    A 'pipeline product key' or list of keys representing values to be passed
    as arguments to :meth:`next`.

The sections other than 'pipeline' in the configuration contain the parameter
for the various tasks, as specified be the 'params' keys.

Execution Order
---------------

When the above pipeline is executed is produces the following output.

>>> local_tasks.update(globals())  # Required for interactive sessions.
>>> Manager.from_yaml_str(spam_config).run()
Setting up PrintEggs.
Setting up GetEggs.
Setting up CookEggs.
Spam and green eggs.
Cooking fried green eggs.
Spam and duck eggs.
Cooking fried duck eggs.
Spam and ostrich eggs.
Cooking fried ostrich eggs.
Finished PrintEggs.
Finished GetEggs.
Finished CookEggs.

The rules for execution order are as follows:

1. One of the methods `setup()`, `next()` or `finish()`, as appropriate, will
   be executed from each task, in order.
2. If the task method is missing its input, as specified by the 'requires' or 'in'
   keys, restart at the beginning of the `tasks` list.
3. If the input to `next()` is missing and the task is at the beginning of the
   list there will be no opportunity to generate this input. Stop iterating
   `next()` and proceed to `finish()`.
4. Once a task has executed `finish()`, remove it from the list.
5. Once a method from the last member of the `tasks` list is executed, restart
   at the beginning of the list.

If the above rules seem somewhat opaque, consider the following example which
illustrates these rules in a pipeline with a slightly more non-trivial flow.

>>> class DoNothing(TaskBase):
...
...     def setup(self):
...         print("Setting up DoNothing.")
...
...     def next(self, input):
...         print("DoNothing next.")
...
...     def finish(self):
...         print("Finished DoNothing.")

>>> local_tasks.update(globals())  # Required for interactive sessions only.
>>> new_spam_config = '''
... pipeline :
...     tasks:
...         -   type:   GetEggs
...             params: eggs_params
...             out:    egg
...
...         -   type:   CookEggs
...             params: cook_params
...             in:     egg
...
...         -   type:   DoNothing
...             params: no_params
...             in:     non_existent_data_product
...
...         -   type:   PrintEggs
...             params: eggs_params
...
... eggs_params:
...     eggs: ['green', 'duck', 'ostrich']
...
... cook_params:
...     style: 'fried'
...
... no_params: {}
... '''

The following would error, because the pipeline config is checked for errors, like an 'in' parameter without a
corresponding 'out'::

    Manager.from_yaml_str(new_spam_config).run()

But this is what it would produce otherwise::

    Setting up GetEggs.
    Setting up CookEggs.
    Setting up DoNothing.
    Setting up PrintEggs.
    Cooking fried green eggs.
    Cooking fried duck eggs.
    Cooking fried ostrich eggs.
    Finished GetEggs.
    Finished CookEggs.
    Finished DoNothing.
    Spam and green eggs.
    Spam and duck eggs.
    Spam and ostrich eggs.
    Finished PrintEggs.

Notice that :meth:`DoNothing.next` is never called, since the pipeline never
generates its input, 'non_existent_data_product'.  Once everything before
:class:`DoNothing` has been executed the pipeline notices that there is no
opertunity for 'non_existent_data_product' to be generated and forces
`DoNothing` to proceed to :meth:`finish`. This also unblocks :class:`PrintEggs`
allowing it to proceed normally.

Pure Python Pipelines
---------------------

It is possible to construct and run a pipeline purely within Python, which can be
useful for quick prototyping and debugging. This gives direct control over task
construction and configuration, and allows injection and inspection of pipeline
products.

To add a task to the pipeline you need to: create an instance of it; set any
configuration attributes directly (or call :meth:`~TaskBase.read_config` on an
appropriate dictionary); and then added to the pipeline using the
:meth:`~Manager.add_task` to add the instance and specify the queues it connects to.

To inject products into the pipeline, use the :class:`~Input` and supply it an
iterator as an argument. Each item will be fed into the pipeline one by one. To take
outputs from the pipeline, simply use the :class:`~Output` task. By default this
simply saves everything it receives into a list, but it can be given a callback
function to apply processing to each argument in turn.

>>> m = Manager()
>>> m.add_task(Input(["platypus", "dinosaur"]), out="key1")
>>> cook = CookEggs()
>>> cook.style = "coddled"
>>> m.add_task(cook, in_="key1")
>>> m.add_task(Output(lambda x: print("I love %s eggs!" % x)), in_="key1")
>>> m.run()
Setting up CookEggs.
Cooking coddled platypus eggs.
I love platypus eggs!
Cooking coddled dinosaur eggs.
I love dinosaur eggs!
Finished CookEggs.

Advanced Tasks
--------------

Several subclasses of :class:`TaskBase` provide advanced functionality for tasks that
conform to the most common patterns. This functionality includes: optionally
reading inputs from disk, instead of receiving them from the pipeline;
optionally writing outputs to disk automatically; and caching the results of a
large computation to disk in an intelligent manner (not yet implemented).

Base classes providing this functionality are :class:`SingleBase` for 'one
shot' tasks and :class:`IterBase` for task that need to iterate.  There are
limited to a single input ('in' key) and a single output ('out' key).  Method
:meth:`~SingleBase.process` should be overwritten instead of :meth:`next`.
Optionally, :meth:`~SingleBase.read_input` and :meth:`~SingleBase.write_output`
may be over-ridden for maximum functionality.  :meth:`setup` and :meth:`finish`
may be overridden as usual.

In addition :class:`SingleH5Base`, :class:`IterH5Base`, provide the
:meth:`read_input` and :meth:`write_output` methods for the most common
formats.

See the documentation for these base classes for more details.

"""

import importlib
import inspect
import logging
import os
import queue
import warnings
from copy import deepcopy

import yaml

from . import config, fileformats, misc


# Set the module logger.
logger = logging.getLogger(__name__)


# Search this dictionary for tasks.
# Used for interactive sessions when task can't be specified by absolute path.
local_tasks = {}


# Exceptions
# ----------


class PipelineConfigError(config.CaputConfigError):
    """Deprecated. Raised when there is an error setting up a pipeline."""

    def __init__(self, message):
        warnings.warn(
            "caput.pipeline.PipelineConfigError is deprecated. It will get removed in December 2021. "
            "Use caput.config.CaputConfigError instead.",
            DeprecationWarning,
            2,
        )
        super().__init__(message)


class PipelineRuntimeError(Exception):
    """Raised when there is a pipeline related error at runtime."""

    pass


class PipelineStopIteration(Exception):
    """This stops the iteration of `next()` in pipeline tasks.

    Pipeline tasks should raise this excetions in the `next()` method to stop
    the iteration of the task and to proceed to `finish()`.

    Note that if `next()` recieves input data as an argument, it is not
    required to ever raise this exception.  The pipeline will proceed to
    `finish()` once the input data has run out.

    """

    pass


class _PipelineMissingData(Exception):
    """Used for flow control when input data is yet to be produced."""

    pass


class _PipelineFinished(Exception):
    """Raised by tasks that have been completed."""

    pass


# Pipeline Manager
# ----------------


def _get_versions(modules):
    """
    Get the versions of a list of python modules.

    Parameters
    ----------
    modules : List[str]
        Names of python modules.

    Returns
    -------
    Dict[str, str]
    """
    if isinstance(modules, str):
        modules = [modules]
    if not isinstance(modules, list):
        raise config.CaputConfigError(
            "Value of 'save_versions' is of type '{}' (expected 'str' or 'list(str)').".format(
                type(modules).__name__
            )
        )
    versions = {}
    for module in modules:
        if not isinstance(module, str):
            raise config.CaputConfigError(
                "Found value of type '{}' in list 'save_versions' (expected 'str').".format(
                    type(module).__name__
                )
            )
        try:
            versions[module] = importlib.import_module(module).__version__
        except ModuleNotFoundError as err:
            raise config.CaputConfigError(
                "Failure getting versions requested with config parameter 'save_versions': {}".format(
                    err
                )
            )
    return versions


class Manager(config.Reader):
    """Pipeline manager for setting up and running pipeline tasks.

    The manager is in charge of initializing all pipeline tasks, setting them
    up by providing the appropriate parameters, then executing the methods of
    the each task in the appropriate order. It also handles intermediate data
    products and ensuring that the correct products are passed between tasks.

    Attributes
    ----------
    logging : Dict(str, str)
        Log levels per module. The key "root" stores the root log level.
    multiprocessing : int
        TODO
    cluster : dict
        TODO
    tasks : list
        Configuration of pipeline tasks.
    save_versions : list
        Module names (str). This list together with the version strings from these
        modules are attached to output metadata. Default: [].
    save_config : bool
        If this is True, the global pipeline configuration is attached to output
        metadata. Default: True.
    psutil_profiling : bool
        Use psutil to profile CPU and memory usage. Default `False`.
    """

    logging = config.logging_config(default={"root": "WARNING"})
    multiprocessing = config.Property(default=1, proptype=int)
    cluster = config.Property(default={}, proptype=dict)
    task_specs = config.Property(default=[], proptype=list, key="tasks")

    # Options to be stored in self.all_tasks_params
    versions = config.Property(default=[], proptype=_get_versions, key="save_versions")
    save_config = config.Property(default=True, proptype=bool)

    def __init__(self, psutil_profiling=False):
        # Initialise the list of task instances
        self.tasks = []
        self.all_params = []
        self.all_tasks_params = []

        self._psutil_profiling = psutil_profiling

        logger.debug(
            f"CPU and memory profiling using psutil {'enabled' if self._psutil_profiling else 'disabled'}."
        )

    @classmethod
    def from_yaml_file(cls, file_name, lint=False, psutil_profiling=False):
        """Initialize the pipeline from a YAML configuration file.

        Parameters
        ----------
        file_name: string
            Path to YAML pipeline configuration file.
        lint : bool
            Instantiate Manager only to lint config. Disables debug logging.
        psutil_profiling : bool
            Use psutil to profile CPU and memory usage

        Returns
        -------
        self: Pipeline object
        """

        try:
            with open(file_name) as f:
                yaml_doc = f.read()
        except TypeError as e:
            raise config.CaputConfigError(
                "Unable to open yaml file ({}): {}".format(file_name, e),
                file_=file_name,
            )
        return cls.from_yaml_str(yaml_doc, lint, psutil_profiling)

    @classmethod
    def from_yaml_str(cls, yaml_doc, lint=False, psutil_profiling=False):
        """Initialize the pipeline from a YAML configuration string.

        Parameters
        ----------
        yaml_doc: string
            Yaml configuration document.
        lint : bool
            Instantiate Manager only to lint config. Disables debug logging.
        psutil_profiling : bool
            Use psutil to profile CPU and memory usage.

        Returns
        -------
        self: Pipeline object
        """
        from .config import SafeLineLoader

        yaml_params = yaml.load(yaml_doc, Loader=SafeLineLoader)
        try:
            if not isinstance(yaml_params["pipeline"], dict):
                raise config.CaputConfigError(
                    "Value 'pipeline' in YAML configuration is of type '{}' (expected a YAML block here).".format(
                        type(yaml_params["pipeline"]).__name__
                    ),
                    location=yaml_params,
                )
        except TypeError as e:
            raise config.CaputConfigError(
                "Couldn't find key 'pipeline' in YAML configuration document.",
                location=yaml_params,
            ) from e
        self = cls.from_config(
            yaml_params["pipeline"], psutil_profiling=psutil_profiling
        )
        self.all_params = yaml_params
        self.all_tasks_params = {
            "versions": self.versions,
            "pipeline_config": self.all_params if self.save_config else None,
        }
        self._setup_logging(lint)
        self._setup_tasks()

        return self

    def _setup_logging(self, lint=False):
        """
        Set up logging based on the config.

        Parameters
        ----------
        lint : bool
            Instantiate Manager only to lint config. Disables debug logging.
        """
        # set root log level and set up default formatter
        loglvl_root = self.logging.get("root", "WARNING")

        # Don't allow INFO log level when linting
        if lint and loglvl_root == "DEBUG":
            loglvl_root = "INFO"

        logging.basicConfig(level=getattr(logging, loglvl_root))
        for module, level in self.logging.items():
            if module != "root":
                logging.getLogger(module).setLevel(getattr(logging, level))

    def run(self):
        """Main driver method for the pipeline.

        This function initializes all pipeline tasks and runs the pipeline
        through to completion.

        Raises
        ------
        PipelineRuntimeError
            If a task stage returns the wrong number of outputs.

        """

        # Run the pipeline.
        while self.tasks:
            for task in list(self.tasks):  # Copy list so we can alter it.
                # These lines control the flow of the pipeline.
                from .profile import PSUtilProfiler

                name_profiling = f"{task.__class__.__name__}.{task._pipeline_state}"

                if hasattr(task, "log"):
                    psutil_log = task.log
                else:
                    psutil_log = logging
                with PSUtilProfiler(
                    self._psutil_profiling, name_profiling, logger=psutil_log
                ):
                    try:
                        out = task._pipeline_next()
                    except _PipelineMissingData:
                        if self.tasks.index(task) == 0:
                            msg = (
                                "%s missing input data and is at beginning of"
                                " task list. Advancing state." % task.__class__.__name__
                            )
                            logger.debug(msg)
                            task._pipeline_advance_state()
                        break
                    except _PipelineFinished:
                        self.tasks.remove(task)
                        continue
                # Now pass the output data products to any task that needs them.
                out = self._check_task_output(out, task)
                if out is None:
                    continue
                keys = str(task._out_keys)
                msg = "%s produced output data product with keys %s."
                msg = msg % (task.__class__.__name__, keys)
                logger.debug(msg)
                for receiving_task in self.tasks:
                    receiving_task._pipeline_inspect_queue_product(task._out_keys, out)

    @staticmethod
    def _check_task_output(out, task):
        """
        Check if task stage's output is as expected.

        Returns
        -------
        out : Same as `TaskBase.next` or None
            Pipeline product. None if there's no output of that task stage that has to be handled further.

        Raises
        ------
        PipelineRuntimeError
            If a task stage returns the wrong number of outputs.
        """
        if out is None:  # This iteration supplied no output
            return None
        elif len(task._out_keys) == 0:  # Output not handled by pipeline.
            return None
        elif len(task._out_keys) == 1:
            if isinstance(task._out_keys, tuple):
                # in config file, written as `out: out_key`, No
                # unpacking if `out` is a length 1 sequence.
                return (out,)
            else:  # `out_keys` is a list.
                # In config file, written as `out: [out_key,]`.
                # `out` must be a length 1 sequence.
                return out
        elif len(task._out_keys) != len(out):
            raise PipelineRuntimeError(
                f"Found unexpected number of outputs in {task.__class__.__name__}"
                f"(got {len(out)} expected {len(task._out_keys)})"
            )
        return out

    def _setup_tasks(self):
        """Create and setup all tasks from the task list."""

        all_out_values = {t.get("out", None) for t in self.task_specs}

        # Setup all tasks in the task listk
        for ii, task_spec in enumerate(self.task_specs):
            try:
                task, key_spec = self._setup_task(task_spec)
                requires = key_spec.get("requires", None)
                in_ = key_spec.get("in", None)
                out = key_spec.get("out", None)
                self._validate_task(task, in_, requires, all_out_values)
                self.add_task(
                    task,
                    requires=requires,
                    in_=in_,
                    out=out,
                )
            except config.CaputConfigError as e:
                msg = "Setting up task {} caused an error:\n\t{}".format(ii, str(e))
                raise config.CaputConfigError(
                    msg, location=task_spec if e.line is None else e.line
                ) from e

    @staticmethod
    def _validate_task(task, in_, requires, all_out_values):
        # Make sure this tasks in/requires values have corresponding out keys from another task
        for key, value in (["in", in_], ["requires", requires]):
            if value is not None:
                if not isinstance(value, list):
                    value = [value]
                for v in value:
                    if v not in all_out_values:
                        raise config.CaputConfigError(
                            "Value '{}' for task {} has no corresponding 'out' from another task "
                            "(Value {} is not in {}).".format(
                                key, type(task), v, all_out_values
                            )
                        )

    def _setup_task(self, task_spec):
        """Set up a pipeline task from the spec given in the tasks list."""

        # Check that only the expected keys are in the task spec.
        for key in task_spec.keys():
            if key not in ["type", "params", "requires", "in", "out"]:
                raise config.CaputConfigError(
                    "Task got an unexpected key '{}' in 'tasks' list.".format(key)
                )

        # 'type' is a required key.
        try:
            task_path = task_spec["type"]
        except KeyError as e:
            raise config.CaputConfigError("'type' not specified for task.") from e

        # Find the tasks class either in the local set, or by importing a fully
        # qualified class name
        if task_path in local_tasks:
            task_cls = local_tasks[task_path]
        else:
            try:
                task_cls = misc.import_class(task_path)
            except (config.CaputConfigError, AttributeError, ModuleNotFoundError) as e:
                msg = "Loading task '%s' caused error %s:\n\t%s" % (
                    task_path,
                    e.__class__.__name__,
                    str(e),
                )
                raise config.CaputConfigError(msg) from e

        # Get the parameters and initialize the class.
        params = {}
        if "params" in task_spec:

            # If params is a dict, assume params are inline
            if isinstance(task_spec["params"], dict):
                params.update(task_spec["params"])

            # Otherwise assume it's a list of keys
            else:

                param_keys = task_spec["params"]

                # Must be a list of keys, convert if only one key was specified.
                if not isinstance(param_keys, list):
                    param_keys = [param_keys]

                # Locate param sections, and add to dict
                for param_key in param_keys:
                    try:
                        params.update(self.all_params[param_key])
                    except KeyError as e:
                        msg = "Parameter group %s not found in config." % param_key
                        raise config.CaputConfigError(msg) from e

        # add global params to params
        task_params = deepcopy(self.all_tasks_params)
        task_params.update(params)

        # Filter just the specifications for the input/output keys
        key_spec = {
            k: v for k, v in task_spec.items() if k in ["requires", "in", "out"]
        }

        # Create and configure the task instance
        try:
            task = task_cls._from_config(task_params)
        except config.CaputConfigError as e:
            raise config.CaputConfigError(
                "Failed instantiating %s from config:\n\t%s" % (task_cls, e),
                location=task_spec.get("params", task_spec),
            ) from e

        return task, key_spec

    def add_task(self, task, requires=None, in_=None, out=None):
        """Add a task instance to the pipeline.

        Parameters
        ----------
        task : TaskBase
            A pipeline task instance.
        requires, in_, out : list or string
            The names of the task inputs and outputs.

        Raises
        ------
        caput.config.CaputConfigError
            If there was an error in the task configuration.
        """
        try:
            task._setup_keys(requires=requires, in_=in_, out=out)
        except Exception as e:
            msg = "Setting up keys for task {} caused an error:\n\t{}".format(
                task.__class__.__name__, str(e)
            )
            raise config.CaputConfigError(msg) from e

        # The tasks own custom validation method
        task.validate()

        self.tasks.append(task)
        logger.debug(f"Added {task.__class__.__name__} to task list.")


# Pipeline Task Base Classes
# --------------------------


class TaskBase(config.Reader):
    """Base class for all pipeline tasks.

    All pipeline tasks should inherit from this class, with functionality and
    analysis added by over-riding `__init__`, `setup`, `next` and/or
    `finish`.

    In addition, input parameters may be specified by adding class attributes
    which are instances of `config.Property`. These will then be read from the
    pipeline yaml file when the pipeline is initialized.  The class attributes
    will be overridden with instance attributes with the same name but with the
    values specified in the pipeline file.
    """

    # Overridable Attributes
    # -----------------------

    def __init__(self):
        """Initialize pipeline task.

        May be overridden with no arguments.  Will be called after any
        `config.Property` attributes are set and after 'input' and 'requires'
        keys are set up.

        """

        pass

    def setup(self, requires=None):
        """First analysis stage of pipeline task.

        May be overridden with any number of positional only arguments
        (defaults are allowed).  Pipeline data-products will be passed as
        specified by `requires` keys in the pipeline setup.

        Any return values will be treated as pipeline data-products as
        specified by the `out` keys in the pipeline setup.

        """

        pass

    def validate(self):
        """Validate the task after instantiation."""

    def next(self, input=None):
        """Iterative analysis stage of pipeline task.

        May be overridden with any number of positional only arguments
        (defaults are allowed).  Pipeline data-products will be passed as
        specified by `in` keys in the pipeline setup.

        Function will be called repetitively until it either raises a
        `PipelineStopIteration` or, if accepting inputs, runs out of input
        data-products.

        Any return values will be treated as pipeline data-products as
        specified by the `out` keys in the pipeline setup.

        """

        raise PipelineStopIteration()

    def finish(self):
        """Final analysis stage of pipeline task.

        May be overridden with no arguments.

        Any return values will be treated as pipeline data-products as
        specified by the `out` keys in the pipeline setup.

        """

        pass

    @property
    def embarrassingly_parallelizable(self):
        """Override to return `True` if `next()` is trivially parallelizeable.

        This property tells the pipeline that the problem can be parallelized
        trivially. This only applies to the `next()` method, which should not
        change the state of the task.

        If this returns `True`, then the Pipeline will execute `next()` many
        times  in parallel and handle all the intermediate data efficiently.
        Otherwise `next()` must be parallelized internally if at all. `setup()`
        and `finish()` must always be parallelized internally.

        Usage of this has not implemented.

        """

        return False

    @property
    def cacheable(self):
        """Override to return `True` if caching results is implemented.

        No caching infrastructure has yet been implemented.

        """

        return False

    # Pipeline Infrastructure
    # -----------------------

    @classmethod
    def _from_config(cls, config):
        self = cls.__new__(cls)
        # Check for unused keys, but ignore the ones not put there by the user.
        self.read_config(config, compare_keys=["versions", "pipeline_config"])
        self.__init__()
        return self

    def _setup_keys(self, in_=None, out=None, requires=None):
        """Setup the 'requires', 'in' and 'out' keys for this task."""

        # Put pipeline in state such that `setup` is the next stage called.
        self._pipeline_advance_state()
        # Parse the task spec.
        requires = _format_product_keys(requires)
        in_ = _format_product_keys(in_)
        out = _format_product_keys(out)
        # Inspect the `setup` method to see how many arguments it takes.
        setup_argspec = inspect.getfullargspec(self.setup)
        # Make sure it matches `requires` keys list specified in config.
        n_requires = len(requires)
        try:
            len_defaults = len(setup_argspec.defaults)
        except TypeError:  # defaults is None
            len_defaults = 0
        min_req = len(setup_argspec.args) - len_defaults - 1
        if n_requires < min_req:
            msg = (
                "Didn't get enough 'requires' keys. Expected at least"
                " %d and only got %d." % (min_req, n_requires)
            )
            raise config.CaputConfigError(msg)
        if n_requires > len(setup_argspec.args) - 1 and setup_argspec.varargs is None:
            msg = "Got too many 'requires' keys. Expected at most %d and" " got %d." % (
                len(setup_argspec.args) - 1,
                n_requires,
            )
            raise config.CaputConfigError(msg)
        # Inspect the `next` method to see how many arguments it takes.
        next_argspec = inspect.getfullargspec(self.next)
        # Make sure it matches `in` keys list specified in config.
        n_in = len(in_)
        try:
            len_defaults = len(next_argspec.defaults)
        except TypeError:  # defaults is None
            len_defaults = 0
        min_in = len(next_argspec.args) - len_defaults - 1
        if n_in < min_in:
            msg = (
                "Didn't get enough 'in' keys. Expected at least"
                " %d and only got %d." % (min_in, n_in)
            )
            raise config.CaputConfigError(msg)
        if n_in > len(next_argspec.args) - 1 and next_argspec.varargs is None:
            msg = "Got too many 'in' keys. Expected at most %d and" " got %d." % (
                len(next_argspec.args) - 1,
                n_in,
            )
            raise config.CaputConfigError(msg)
        # Now that all data product keys have been verified to be valid, store
        # them on the instance.
        self._requires_keys = requires
        self._requires = [None] * n_requires
        self._in_keys = in_
        self._in = [queue.Queue() for i in range(n_in)]
        self._out_keys = out

    def _pipeline_advance_state(self):
        """Advance this pipeline task to the next stage.

        The task stages are 'setup', 'next', 'finish' or 'raise'.  This
        method sets the state of the task, advancing it to the next stage.

        Also performs some clean up tasks and checks associated with changing
        stages.

        """

        if not hasattr(self, "_pipeline_state"):
            self._pipeline_state = "setup"
        elif self._pipeline_state == "setup":
            # Delete inputs to free memory.
            self._requires = None
            self._pipeline_state = "next"
        elif self._pipeline_state == "next":
            # Make sure input queues are empty then delete them so no more data
            # can be queued.
            for in_, in_key in zip(self._in, self._in_keys):
                if not in_.empty():
                    msg = (
                        "Task finished %s iterating `next()` but input queue '%s' isn't empty."
                        % (self.__class__.__name__, in_key)
                    )
                    warnings.warn(msg)

            self._in = None
            self._pipeline_state = "finish"
        elif self._pipeline_state == "finish":
            self._pipeline_state = "raise"
        elif self._pipeline_state == "raise":
            pass
        else:
            raise PipelineRuntimeError()

    def _pipeline_next(self):
        """Execute the next stage of the pipeline.

        Execute `setup()`, `next()`, `finish()` or raise `PipelineFinished`
        depending on the state of the task.  Advance the state to the next
        stage if applicable.

        """

        if self._pipeline_state == "setup":
            # Check if we have all the required input data.
            for req in self._requires:
                if req is None:
                    raise _PipelineMissingData()
            msg = "Task %s calling 'setup()'." % self.__class__.__name__
            logger.debug(msg)
            out = self.setup(*tuple(self._requires))
            self._pipeline_advance_state()
            return out
        elif self._pipeline_state == "next":
            # Check if we have all the required input data.
            for in_ in self._in:
                if in_.empty():
                    raise _PipelineMissingData()
            # Get the next set of data to be run.
            args = ()
            for in_ in self._in:
                args += (in_.get(),)
            try:
                msg = "Task %s calling 'next()'." % self.__class__.__name__
                logger.debug(msg)
                out = self.next(*args)
                return out
            except PipelineStopIteration:
                # Finished iterating `next()`.
                self._pipeline_advance_state()
                return None
        elif self._pipeline_state == "finish":
            msg = "Task %s calling 'finish()'." % self.__class__.__name__
            logger.debug(msg)
            out = self.finish()
            self._pipeline_advance_state()
            return out
        elif self._pipeline_state == "raise":
            raise _PipelineFinished()
        else:
            raise PipelineRuntimeError()

    def _pipeline_inspect_queue_product(self, keys, products):
        """Inspect data products and queue them as inputs if applicable.

        Compare a list of data products keys to the keys expected by this task
        as inputs to `setup()` ('requires') and `next()` ('in').  If there is a
        match, store the corresponding data product to be used in the next
        invocation of these methods.

        """

        n_keys = len(keys)
        for ii in range(n_keys):
            key = keys[ii]
            product = products[ii]
            for jj, requires_key in enumerate(self._requires_keys):
                if requires_key == key:
                    # Make sure that `setup()` hasn't already been run or this
                    # data product already set.
                    msg = "%s stowing data product with key %s for 'requires'."
                    msg = msg % (self.__class__.__name__, key)
                    logger.debug(msg)
                    if self._requires is None:
                        msg = (
                            "Tried to set 'requires' data product, but"
                            "`setup()` already run."
                        )
                        raise PipelineRuntimeError(msg)
                    if not self._requires[jj] is None:
                        msg = "'requires' data product set more than once."
                        raise PipelineRuntimeError(msg)
                    else:
                        # Accept the data product and store for later use.
                        self._requires[jj] = product
            for jj, in_key in enumerate(self._in_keys):
                if in_key == key:
                    msg = "%s queue data product with key %s for 'in'."
                    msg = msg % (self.__class__.__name__, key)
                    logger.debug(msg)
                    # Check that task is still accepting inputs.
                    if self._in is None:
                        msg = (
                            "Tried to queue 'requires' data product, but"
                            "`next()` iteration already completed."
                        )
                        raise PipelineRuntimeError(msg)
                    else:
                        # Accept the data product and store for later use.
                        self._in[jj].put(product)


class _OneAndOne(TaskBase):
    """Base class for tasks that have (at most) one input and one output

    This is not a user base class and simply holds code that is common to
    `SingleBase` and `IterBase`.
    """

    input_root = config.Property(default="None", proptype=str)
    output_root = config.Property(default="None", proptype=str)
    output_format = config.file_format()
    output_compression = config.Property(default=None, proptype=str)
    output_compression_opts = config.Property(default=None)

    def __init__(self):
        # Inspect the `process` method to see how many arguments it takes.
        pro_argspec = inspect.getfullargspec(self.process)
        n_args = len(pro_argspec.args) - 1
        if n_args == 0:
            self._no_input = True
        else:
            self._no_input = False

    def process(self, input):
        """Override this method with your data processing task."""

        output = input
        return output

    def validate(self):
        """
        Validate the task after instantiation.

        May be overriden to add any special task validation before the task is run.
        This is called by the :py:class:`Manager` after it's added to the pipeline and has special attributes like
        `_requires_keys`, `_requires`, `_in_keys`, `_in`, `-_out_keys` set.
        Call `super().validate()` if you overwrite this.

        Raises
        ------
        caput.config.CaputConfigError
            If there was an error in the task configuration.
        """
        # Inspect the `process` method to see how many arguments it takes.
        pro_argspec = inspect.getfullargspec(self.process)
        n_args = len(pro_argspec.args) - 1

        if n_args > 1:
            msg = "`process` method takes more than 1 argument, which is not allowed."
            raise config.CaputConfigError(msg)
        if (
            pro_argspec.varargs
            or pro_argspec.varkw
            or pro_argspec.kwonlyargs
            or pro_argspec.defaults
        ):
            msg = (
                "`process` method may not have variable length or optional"
                " arguments."
            )
            raise config.CaputConfigError(msg)

        # Make sure we know where to get the data from.
        if self.input_root == "None":
            if len(self._in) != n_args:
                msg = (
                    "No data to iterate over. 'input_root' is 'None' and"
                    " there are no 'in' keys."
                )
                raise config.CaputConfigError(msg)
        else:
            if len(self._in) != 0:
                msg = (
                    "For data input, supplied both a file path and an 'in'"
                    " key.  If not reading to disk, set 'input_root' to"
                    " 'None'."
                )
                raise config.CaputConfigError(msg)
            if n_args != 1:
                msg = (
                    "Reading input from disk but `process` method takes no"
                    " arguments."
                )
                raise config.CaputConfigError(msg)

    def read_process_write(self, input, input_filename, output_filename):
        """Reads input, executes any processing and writes output."""

        # Read input if needed.
        if input is None and not self._no_input:
            if input_filename is None:
                raise RuntimeError("No file to read from.")
            input_filename = self.input_root + input_filename
            input_filename = os.path.expanduser(input_filename)
            logger.info(
                "%s reading data from file %s.", self.__class__.__name__, input_filename
            )
            input = self.read_input(input_filename)
        # Analyse.
        if self._no_input:
            if input is not None:
                # This should never happen.  Just here to catch bugs.
                raise RuntimeError("Somehow `input` was set.")
            output = self.process()
        else:
            output = self.process(input)
        # Write output if needed.
        if self.output_root != "None" and output is not None:
            if output_filename is None:
                raise RuntimeError("No file to write to.")
            output_filename = self.output_root + output_filename
            output_filename = os.path.expanduser(output_filename)
            logger.info(
                "%s writing data to file %s.", self.__class__.__name__, output_filename
            )
            output_dirname = os.path.dirname(output_filename)
            if not os.path.isdir(output_dirname):
                os.makedirs(output_dirname)
            self.write_output(
                output_filename,
                output,
                file_format=self.output_format,
                compression=self.output_compression,
                compression_opts=self.output_compression_opts,
            )
        return output

    def read_input(self, filename):
        """Override to implement reading inputs from disk."""

        raise NotImplementedError()

    def cast_input(self, input):
        """Override to support accepting pipeline inputs of variouse types."""

        return input

    def read_output(self, filename):
        """Override to implement reading outputs from disk.

        Used for result cacheing.

        """

        raise NotImplementedError()

    @staticmethod
    def write_output(filename, output, file_format=None, **kwargs):
        """Override to implement reading inputs from disk."""

        raise NotImplementedError()


class SingleBase(_OneAndOne):
    """Base class for non-iterating tasks with at most one input and output.

    Inherits from :class:`TaskBase`.

    Tasks inheriting from this class should override `process` and optionally
    :meth:`setup`, :meth:`finish`, :meth:`read_input`, :meth:`write_output` and
    :meth:`cast_input`.  They should not override :meth:`next`.

    If the value of :attr:`input_root` is anything other than the string "None"
    then the input will be read (using :meth:`read_input`) from the file
    ``self.input_root + self.input_filename``.  If the input is specified both as
    a filename and as a product key in the pipeline configuration, an error
    will be raised upon initialization.


    If the value of :attr:`output_root` is anything other than the string
    "None" then the output will be written (using :meth:`write_output`) to the
    file ``self.output_root + self.output_filename``.

    Attributes
    ----------
    input_root : string
        Pipeline settable parameter giving the first part of the input path.
        If set to 'None' no input is read. Either it is assumed that no input
        is required or that input is recieved from the pipeline.
    input_filename : string
        Pipeline settable parameter giving the last part of input path. The
        full input path is ``self.input_root + self.input_filename``.
    output_root : strig
        Pipeline settable parameter giving the first part of the output path.
        If set to 'None' no output is written.
    output_filename : string
        Pipeline settable parameter giving the last part of output path. The
        full output path is ``self.output_root + self.output_filename``.
    """

    input_filename = config.Property(default="", proptype=str)
    output_filename = config.Property(default="", proptype=str)
    output_format = config.file_format()
    output_compression = config.Property(default=None, proptype=str)
    output_compression_opts = config.Property(default=None)

    def next(self, input=None):
        """Should not need to override."""

        # This should only be called once.
        try:
            if self.done:
                raise PipelineStopIteration()
        except AttributeError:
            self.done = True

        if input:
            input = self.cast_input(input)
        return self.read_process_write(input, self.input_filename, self.output_filename)


class IterBase(_OneAndOne):
    """Base class for iterating tasks with at most one input and one output.

    Tasks inheriting from this class should override :meth:`process` and
    optionally :meth:`setup`, :meth:`finish`, :meth:`read_input`,
    :meth:`write_output` and :meth:`cast_input`. They should not override
    :meth:`next`.

    If the value of :attr:`input_root` is anything other than the string "None"
    then the input will be read (using :meth:`read_input`) from the file
    ``self.input_root + self.file_middles[i] + self.input_ext``.  If the
    input is specified both as a filename and as a product key in the pipeline
    configuration, an error will be raised upon initialization.

    If the value of :attr:`output_root` is anything other than the string "None"
    then the output will be written (using :meth:`write_output`) to the file
    ``self.output_root + self.file_middles[i] + self.output_ext``.

    Attributes
    ----------
    iteration : int
        The current iteration of `process`/`next`.
    file_middles : list of strings
        The unique part of each file path.
    input_root : string
        Pipeline settable parameter giving the first part of the input path.
        If set to 'None' no input is read. Either it is assumed that no input
        is required or that input is recieved from the pipeline.
    input_ext : string
        Pipeline settable parameter giving the last part of input path. The
        full input path is ``self.input_root +
        self.file_middles[self.iteration] + self.input_ext``.
    output_root : strig
        Pipeline settable parameter giving the first part of the output path.
        If set to 'None' no output is written.
    output_ext : string
        Pipeline settable parameter giving the last part of output path. The
        full output path is ``self.output_root +
        self.file_middles[self.iteration] + self.output_ext``.
    """

    file_middles = config.Property(default=[], proptype=list)
    input_ext = config.Property(default="", proptype=str)
    output_ext = config.Property(default="", proptype=str)

    def __init__(self):
        super().__init__()
        self.iteration = 0

    def next(self, input=None):
        """Should not need to override."""

        # Sort out filenames.
        if self.iteration >= len(self.file_middles):
            if not self.input_root == "None":
                # We are iterating over input files and have run out.
                raise PipelineStopIteration()
            else:
                # Not iterating over input files, and unable to assign
                # filenames.
                input_filename = None
                output_filename = None
        else:
            # May or may not be iterating over input files, but able to assign
            # filenames.
            middle = self.file_middles[self.iteration]
            input_filename = middle + self.input_ext
            output_filename = middle + self.output_ext

        if input:
            input = self.cast_input(input)
        output = self.read_process_write(input, input_filename, output_filename)
        self.iteration += 1
        return output


class H5IOMixin:
    """Provides hdf5/zarr IO for pipeline tasks.

    As a mixin, this must be combined (using multiple inheritance) with a
    subclass of `TaskBase`, providing the full task API.

    Provides the methods `read_input`, `read_output` and `write_output` for
    hdf5 data.

    """

    # TODO, implement reading on disk (i.e. no copy to memory).
    # ondisk = config.Property(default=False, proptype=bool)

    @staticmethod
    def read_input(filename):
        """Method for reading hdf5 input."""

        from caput import memh5

        return memh5.MemGroup.from_hdf5(filename, mode="r")

    @staticmethod
    def read_output(filename):
        """Method for reading hdf5 output (from caches)."""

        # Replicate code from read_input in case read_input is overridden.
        from caput import memh5

        return memh5.MemGroup.from_hdf5(filename, mode="r")

    @staticmethod
    def write_output(filename, output, file_format=None, **kwargs):
        """
        Method for writing hdf5/zarr output.

        Parameters
        ----------
        filename : str
            File name
        output : memh5.Group, zarr.Group or h5py.Group
            `output` to be written. If this is a `h5py.Group` (which include `hdf5.File` objects)
            the buffer is flushed if `filename` points to the same file and a copy is made otherwise.
        file_format : fileformats.Zarr, fileformats.HDF5 or None
            File format to use. If this is not specified, the file format is guessed based on the type of
            `output` or the `filename`. If guessing is not successful, HDF5 is used.
        """

        from caput import memh5
        import h5py

        file_format = fileformats.check_file_format(filename, file_format, output)

        try:
            import zarr
        except ImportError:
            if file_format == fileformats.Zarr:
                raise RuntimeError("Can't write to zarr file. Please install zarr.")

        # Ensure parent directory is present.
        dirname = os.path.dirname(filename)
        if not os.path.isdir(dirname):
            try:
                os.makedirs(dirname)
            except OSError as e:
                # It's possible the directory was created by another MPI task
                if not os.path.isdir(dirname):
                    raise e
        # Cases for `output` object type.
        if isinstance(output, memh5.MemGroup):
            # Already in memory.

            # Lock file
            with misc.lock_file(filename, comm=output.comm) as fn:
                output.to_file(fn, mode="w", file_format=file_format, **kwargs)
            return

        if isinstance(output, h5py.Group):
            if os.path.isfile(filename) and os.path.samefile(
                output.file.filename, filename
            ):
                # `output` already lives in this file.
                output.flush()

            else:
                # Copy to memory then to disk
                # XXX This can be made much more efficient using a direct copy.
                out_copy = memh5.MemGroup.from_hdf5(output)

                # Lock file as we write
                with misc.lock_file(filename, comm=out_copy.comm) as fn:
                    out_copy.to_hdf5(fn, mode="w")
        elif isinstance(output, zarr.Group):
            if os.path.isdir(filename) and os.path.samefile(
                output.store.path, filename
            ):
                pass
            else:
                logger.debug(f"Copying {output.store}:{output.path} to {filename}.")
                from . import mpiutil

                if mpiutil.rank == 0:
                    n_copied, n_skipped, n_bytes_copied = zarr.copy_store(
                        output.store,
                        zarr.DirectoryStore(filename),
                        source_path=output.path,
                    )
                logger.debug(
                    f"Copied {n_copied} items ({n_bytes_copied} bytes), skipped {n_skipped} items."
                )


class BasicContMixin:
    """Provides IO for BasicCont objects in pipeline tasks.

    As a mixin, this must be combined (using multiple inheritance) with a
    subclass of `TaskBase`, providing the full task API.

    Provides the methods `read_input`, `read_output` and `write_output` for
    BasicCont data which gets written to HDF5 files.

    """

    # TODO, implement reading on disk (i.e. no copy to memory).
    # ondisk = config.Property(default=False, proptype=bool)

    # Private setting for reading of inputs, should be overriden in sub class.
    _distributed = False
    _comm = None

    def read_input(self, filename):
        """Method for reading hdf5 input."""

        from caput import memh5

        return memh5.BasicCont.from_file(
            filename, distributed=self._distributed, comm=self._comm
        )

    def read_output(self, filename):
        """Method for reading hdf5 output (from caches)."""

        # Replicate code from read_input in case read_input is overridden.
        from caput import memh5

        return memh5.BasicCont.from_file(
            filename, distributed=self._distributed, comm=self._comm
        )

    @staticmethod
    def write_output(filename, output, file_format=None, **kwargs):
        """
        Method for writing output to disk.

        Parameters
        ----------
        filename : str
            File name.
        output : :class:`memh5.BasicCont`
            Data to be written.
        file_format : `fileformats.FileFormat`
            File format to use. Default `fileformats.HDF5`.

        Returns
        -------

        """

        from caput import memh5

        file_format = fileformats.check_file_format(filename, file_format, output)

        # Ensure parent directory is present.
        dirname = os.path.dirname(filename)
        if dirname != "" and not os.path.isdir(dirname):
            try:
                os.makedirs(dirname)
            except OSError as e:
                # It's possible the directory was created by another MPI task
                if not os.path.isdir(dirname):
                    raise e
        # Cases for `output` object type.
        if not isinstance(output, memh5.BasicCont):
            raise RuntimeError(
                "Object to write out is not an instance of memh5.BasicCont"
            )

        # Already in memory.
        output.save(filename, file_format=file_format, **kwargs)


class SingleH5Base(H5IOMixin, SingleBase):
    """Base class for tasks with hdf5 input and output.

    Inherits from :class:`H5IOMixin` and :class:`SingleBase`.

    """

    pass


class IterH5Base(H5IOMixin, IterBase):
    """Base class for iterating over hdf5 input and output.

    Inherits from :class:`H5IOMixin` and :class:`IterBase`.

    """

    pass


# Simple tasks for bridging to Python
# -----------------------------------


class Input(TaskBase):
    """Pass inputs into the pipeline from outside."""

    def __init__(self, inputs=None):
        super().__init__()
        self.inputs = inputs or []
        self._iter = None

    def next(self):
        """Pop and return the first element of inputs."""

        if self._iter is None:
            self._iter = iter(self.inputs)

        try:
            return next(self._iter)
        except StopIteration as e:
            raise PipelineStopIteration() from e


class Output(TaskBase):
    """Take outputs from the pipeline and place them in a list.

    To apply some processing to pipeline output (i.e. this tasks input), use the
    `callback` argument which will get passed the item. The return value of the
    callback is placed in the `outputs` attribute. Note that this need not be the
    input, so if pipeline output should be deleted to save memory you can simply
    return `None`.

    Parameters
    ----------
    callback : function, optional
        A function which can apply some processing to the pipeline output.
    """

    def __init__(self, callback=None):
        super().__init__()
        self.outputs = []
        self.callback = callback

    def next(self, in_):
        """Pop and return the first element of inputs."""

        if self.callback:
            in_ = self.callback(in_)

        self.outputs.append(in_)


# Internal Functions
# ------------------


def _format_product_keys(keys):
    """Formats the pipeline task product keys.

    In the pipeline config task list, the values of 'requires', 'in' and 'out'
    are keys representing data products.  This function gets that key from the
    task's entry of the task list, defaults to zero, and ensures it's formated
    as a sequence of strings.

    """

    if keys is None:
        return []

    # Turn into a sequence if only one key was provided.
    if not isinstance(keys, list):
        # Making this a tuple instead of a list is significant.  It only
        # impacts the 'out' product key and affects how return values are
        # unpacked.
        keys = (keys,)

    # Check that all the keys provided are strings.
    for key in keys:
        if not isinstance(key, str):
            msg = "Data product keys must be strings."
            raise config.CaputConfigError(msg)
    return keys


if __name__ == "__main__":
    import doctest

    doctest.testmod()
