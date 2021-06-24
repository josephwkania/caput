"""
An array class for containing MPI distributed array.

Examples
========

This example performs a transfrom from time-freq to lag-m space. This involves
Fourier transforming each of these two axes of the distributed array::

    import numpy as np
    from mpi4py import MPI

    from caput.mpiarray import MPIArray

    nfreq = 32
    nprod = 2
    ntime = 32

    Initialise array with (nfreq, nprod, ntime) global shape
    darr1 = MPIArray((nfreq, nprod, ntime), dtype=np.float64)

    # Load in data into parallel array
    for lfi, fi in darr1.enumerate(axis=0):
        darr1[lfi] = load_freq_data(gfi)

    # Perform m-transform (i.e. FFT)
    darr2 = MPIArray.wrap(np.fft.fft(darr1, axis=1), axis=0)

    # Redistribute to get all frequencies onto each process, this performs the
    # global transpose using MPI to make axis=1 the distributed axis, and make
    # axis=0 completely local.
    darr3 = darr2.redistribute(axis=1)

    # Perform the lag transform on the frequency direction.
    darr4 = MPIArray.wrap(np.fft.irfft(darr3, axis=0), axis=1)

Note: If a user wishes to create an MPIArray from an ndarray, they should use
:py:meth:`MPIArray.wrap`. They should not use `ndarray.view(MPIArray)`.
Attributes will not be set correctly if they do.

Global Slicing
==============

The :class:`MPIArray` also supports slicing with the global index using the
:py:attr:`.MPIArray.global_slice` property. This can be used for both fetching
and assignment with global indices, supporting the basic slicing notation of
`numpy`.

Its behaviour changes depending on the exact slice it gets:

- A full slice (`:`) along the parallel axis returns an :class:`MPIArray` on
  fetching, and accepts an :class:`MPIArray` on assignment.
- A partial slice (`:`) returns and accepts a numpy array on the rank holding
  the data, and :obj:`None` on other ranks.

It's important to note that it never communicates data between ranks. It only
ever operates on data held on the current rank.

Global Slicing Examples
-----------------------

Here is an example of this in action. Create and set an MPI array:

>>> import numpy as np
>>> from caput import mpiarray, mpiutil
>>>
>>> arr = mpiarray.MPIArray((mpiutil.size, 3), dtype=np.float64)
>>> arr[:] = 0.0

>>> for ri in range(mpiutil.size):
...    if ri == mpiutil.rank:
...        print(ri, arr)
...    mpiutil.barrier()
0 [[0. 0. 0.]]

Use a global index to assign to the array

>>> arr.global_slice[3] = 17

Fetch a view of the whole array with a full slice

>>> arr2 = arr.global_slice[:, 2]

Print the third column of the array on all ranks

>>> for ri in range(mpiutil.size):
...    if ri == mpiutil.rank:
...        print(ri, arr2)
...    mpiutil.barrier()
0 [0.]

Fetch a view of the whole array with a partial slice. The final two ranks should be None
>>> arr3 = arr.global_slice[:2, 2]
>>> for ri in range(mpiutil.size):
...    if ri == mpiutil.rank:
...        print(ri, arr3)
...    mpiutil.barrier()
0 [0.]

Direct Slicing
==============

`MPIArray` supports direct slicing using `[...]` (implemented via
:py:meth:`__getitem__` ). This can be used for both fetching and assignment. It is
recommended to only index into the non-parallel axis or to do a full slice `[:]`.

Direct Slicing Behaviour
------------------------

- A full slice `[:]` will return a :class:`MPIArray` on fetching, with
  identical properties to the original array.
- Any indexing or slicing into the non-parallel axis, will also return a
  :class:`MPIArray`. The number associated with the parallel axis,
  will be adjusted if a slice results in an axis reduction.
- Any indexing into the parallel axis is discouraged. This behaviour is
  deprecated. For now, it will result into a local index on each rank,
  returning a regular `numpy` array, along with a warning.
  In the future, it is encouraged to index into the local array
  :py:attr:`MPIArray.local_array`, if you wish to locally index into
  the parallel axis

Direct Slicing Examples
-----------------------

.. deprecated:: 21.04
    Direct indexing into parallel axis is DEPRECATED. For now, it will return a numpy
    array equal to local array indexing, along with a warning. This behaviour will be
    removed in the future.

>>> darr = mpiarray.MPIArray((mpiutil.size,), axis=0)
>>> (darr[0] == darr.local_array[0]).all()
True
>>> not hasattr(darr[0], "axis")
True

If you wish to index into local portion of a distributed array along its parallel
axis, you need to index into the :py:attr:`MPIArray.local_array`.

>>> darr[:] = 1.0
>>> darr.local_array[0]
1.0

indexing into non-parallel axes returns an MPIArray with appropriate attributes
Slicing could result in a reduction of axis, and a lower parallel axis number

>>> darr = mpiarray.MPIArray((4, mpiutil.size), axis=1)
>>> darr[:] = mpiutil.rank
>>> (darr[0] == mpiutil.rank).all()
array([ True])
>>> darr[0].axis == 0
True

ufunc
=====

In NumPy, universal functions (or ufuncs) are functions that operate on ndarrays
in an element-by-element fashion. :class:`MPIArray` supports all ufunc calculations,
except along the parallel axis.

ufunc Requirements
------------------

- All input :class:`MPIArray` *must* be distributed along the same axis.
- If you pass a kwarg `axis` to the ufunc, it must not be the parallel axis.

ufunc Behaviour
---------------

- If no output are provided, the results are converted back to MPIArrays. The new
  array will either be parallel over the same axis as the input MPIArrays, or possibly
  one axis down if the `ufunc` is applied via a `reduce` method (i.e. the shape of the
  array is reduced by one axis).
- For operations that normally reduce to a scalar, the scalars will be wrapped into a 1D
  array distributed across axis 0.
- shape related attributes will be re-calculated.

ufunc Examples
--------------

Create an array

>>> dist_arr = mpiarray.MPIArray((mpiutil.size, 4), axis=0)
>>> dist_arr[:] = mpiutil.rank

Element wise summation and `.all()` reduction

>>> (dist_arr + dist_arr == 2 * mpiutil.rank).all()
array([ True])

Element wise multiplication and reduction

>>> (dist_arr * 2 == 2 * mpiutil.rank).all()
array([ True])

The distributed axis is unchanged during an elementwise operation

>>> (dist_arr + dist_arr).axis == 0
True

An operation on multiple arrays with different parallel axes is not possible and will
result in an exception

>>> (mpiarray.MPIArray((mpiutil.size, 4), axis=0) -
...  mpiarray.MPIArray((mpiutil.size, 4), axis=1))  # doctest: +NORMALIZE_WHITESPACE
Traceback (most recent call last):
...
caput.mpiarray.AxisException: The distributed axis for all MPIArrays in an expression
should be the same

Summation across a non-parallel axis

>>> (dist_arr.sum(axis=1) == 4 * mpiutil.rank).all()
array([ True])

A sum reducing across all axes will reduce across each local array and give a new
distributed array with a single element on each rank.

>>> (dist_arr.sum() == 4 * 3 * mpiutil.rank).all()
array([ True])
>>> (dist_arr.sum().local_shape) == (1,)
True
>>> (dist_arr.sum().global_shape) == (mpiutil.size,)
True

Reduction methods might result in a decrease in the distributed axis number

>>> dist_arr = mpiarray.MPIArray((mpiutil.size, 4, 3), axis=1)
>>> dist_arr.sum(axis=0).axis == 0
True

MPI.Comm
=====

mpi4py.MPI.Comm provides a wide variety of functions for communications across nodes
https://mpi4py.readthedocs.io/en/stable/overview.html?highlight=allreduce#collective-communications

They provide an upper-case and lower-case variant of many functions.
With MPIArrays, please use the uppercase variant of the function. The lower-case variants involve
an intermediate pickling process, which can lead to malformed arrays.

"""
import os
import time
import logging

import numpy as np

from caput import mpiutil, misc


logger = logging.getLogger(__name__)


class _global_resolver:
    # Private class implementing the global sampling for MPIArray

    def __init__(self, array):

        self.array = array
        self.axis = array.axis
        self.offset = array.local_offset[self.axis]
        self.length = array.global_shape[self.axis]

    def _resolve_slice(self, slobj):
        # Transforms a numpy basic slice on the global arrays into a fully
        # fleshed out slice tuple referencing the positions in the local arrays.
        # If a single integer index is specified for the distributed axis, then
        # either the local index is returned, or None if it doesn't exist on the
        # current rank.

        ndim = self.array.ndim
        local_length = self.array.shape[self.axis]

        # Expand a single integer or slice index
        if isinstance(slobj, (int, slice)):
            slobj = (slobj, Ellipsis)

        # Add an ellipsis if length of slice object is too short
        if isinstance(slobj, tuple) and len(slobj) < ndim and Ellipsis not in slobj:
            slobj = slobj + (Ellipsis,)

        # Expand an ellipsis
        slice_list = []
        for sl in slobj:
            if sl is Ellipsis:
                for _ in range(ndim - len(slobj) + 1):
                    slice_list.append(slice(None, None))
            else:
                slice_list.append(sl)

        fullslice = True

        # Process the parallel axis. Calculate the correct index for the
        # containing rank, and set None on all others.
        if isinstance(slice_list[self.axis], int):
            index = slice_list[self.axis] - self.offset
            slice_list[self.axis] = (
                None if (index < 0 or index >= local_length) else index
            )
            fullslice = False

        # If it's a slice, then resolve any offsets
        # If any of start or stop is defined then mark that this is not a complete slice
        # Also mark if there is any actual data on this rank
        elif isinstance(slice_list[self.axis], slice):
            s = slice_list[self.axis]
            start = s.start
            stop = s.stop
            step = s.step

            # Check if start is defined, and modify slice
            if start is not None:
                start = (
                    start if start >= 0 else start + self.length
                )  # Resolve negative indices
                fullslice = False
                start = start - self.offset
            else:
                start = 0

            # Check if stop is defined and modify slice
            if stop is not None:
                stop = (
                    stop if stop >= 0 else stop + self.length
                )  # Resolve negative indices
                fullslice = False
                stop = stop - self.offset
            else:
                stop = local_length

            # If step is defined we don't need to adjust this, but it's no longer a complete slice
            if step is not None:
                fullslice = False

            # If there is no data on this node place None on the parallel axis
            if start >= local_length or stop < 0:
                slice_list[self.axis] = None
            else:
                # Normalise the indices and create slice
                start = max(min(start, local_length), 0)
                stop = max(min(stop, local_length), 0)
                slice_list[self.axis] = slice(start, stop, step)

        return tuple(slice_list), fullslice

    def __getitem__(self, slobj):

        # Resolve the slice object
        slobj, is_fullslice = self._resolve_slice(slobj)

        # If not a full slice, return a numpy array (or None)
        if not is_fullslice:

            # If the distributed axis has a None, that means there is no data at that index on this rank
            if slobj[self.axis] is None:
                return None
            else:
                return self.array.local_array[slobj]

        else:

            # Fix up slobj for axes where there is no data
            slobj = tuple(slice(None, None, None) if sl is None else sl for sl in slobj)

            return self.array[slobj]

    def __setitem__(self, slobj, value):

        slobj, _ = self._resolve_slice(slobj)

        # If the distributed axis has a None, that means that index is not available on
        # this rank
        if slobj[self.axis] is None:
            return
        self.array[slobj] = value


class MPIArray(np.ndarray):
    """A numpy array like object which is distributed across multiple processes.

    Parameters
    ----------
    global_shape : tuple
        The global array shape. The returned array will be distributed across
        the specified index.
    axis : integer, optional
        The dimension to distribute the array across.
    """

    def __getitem__(self, v):
        # Return an MPIArray view

        # ensure slobj is a tuple, with one entry for every axis
        # if smaller than number of axes, extend with `slice(None, None, None)`
        if not isinstance(v, tuple):
            v = (v,)
        if len(v) < len(self.global_shape):
            v = v + (slice(None, None, None),) * (len(self.global_shape) - len(v))

        # __getitem__ should not be receiving sub-slices or direct indexes on the
        # distributed axis. global_slice should be used for both
        dist_axis_index = v[self.axis]
        if (dist_axis_index != slice(None, None, None)) and (
            dist_axis_index != slice(0, self.local_array.shape[self.axis], None)
        ):
            import warnings

            if isinstance(dist_axis_index, int):
                warnings.warn(
                    "You are indexing directly into the distributed axis."
                    "Returning a view into the local array."
                    "Please use global_slice, or .local_array before indexing instead."
                )

                return self.local_array.__getitem__(v)
            warnings.warn(
                "You are directly sub-slicing the distributed axis."
                "Returning a view into the local array."
                "Please use global_slice, or .local_array before indexing."
            )
            return self.local_array.__getitem__(v)

        # Figure out which is the axis number for the distributed axis after the slicing
        # by removing slice axes which are just ints from the mapping.
        # int slices will result in that axis being reduced
        # and the distributed axis number dropping by 1.
        dist_axis = [
            index
            for index, sl in enumerate(v)
            if not isinstance(sl, int) and not isinstance(sl, np.int64)
        ]

        try:
            dist_axis = dist_axis.index(self.axis)
        except ValueError as e:
            raise AxisException(
                "Failed to calculate new distributed axis for output of this slice"
            ) from e

        if dist_axis == self.axis:
            return super().__getitem__(v)

        # the MPIArray array_finalize assumes that the output distributed axis
        # is the same as the source
        # since the number for the distributed axes has changed, we
        # will need a fresh MPIArray object

        arr_sliced = self.local_array.__getitem__(v)

        # determine the shape of the new array
        # grab the length of the distributed axes from the original
        # instead of performing an mpi.allreduce
        new_global_shape = list(arr_sliced.shape)

        # if a single value, not an array, just return
        if not new_global_shape:
            return arr_sliced

        new_global_shape[dist_axis] = self.global_shape[self.axis]

        # create an mpi array, with the appropriate parameters
        # fill it with the contents of the slice
        arr_mpi = MPIArray(
            tuple(new_global_shape), axis=dist_axis, comm=self._comm, dtype=self.dtype
        )
        arr_mpi[:] = arr_sliced[:]
        return arr_mpi

    def __setitem__(self, slobj, value):
        self.local_array.__setitem__(slobj, value)

    def __repr__(self):
        return self.local_array.__repr__()

    def __str__(self):
        return self.local_array.__str__()

    @property
    def global_shape(self):
        """
        Global array shape.

        Returns
        -------
        global_shape : tuple
        """
        return self._global_shape

    @global_shape.setter
    def global_shape(self, var):
        """
        Set global array shape.

        Parameters
        ----------
        var : tuple
        """
        self._global_shape = var

    @property
    def axis(self):
        """
        Axis we are distributed over.

        Returns
        -------
        axis : integer
        """
        return self._axis

    @axis.setter
    def axis(self, var):
        """
        Set axis we are distributed over.

        Parameters
        ----------
        var : int
        """
        self._axis = var

    @property
    def local_shape(self):
        """
        Shape of local section.

        Returns
        -------
        local_shape : tuple
        """
        return self._local_shape

    @local_shape.setter
    def local_shape(self, var):
        """
        Set shape of local section.

        Parameters
        ----------
        var : tuple
        """
        self._local_shape = var

    @property
    def local_offset(self):
        """
        Offset into global array.

        This is equivalent to the global-index of
        the [0, 0, ...] element of the local section.

        Returns
        -------
        local_offset : tuple
        """
        return self._local_offset

    @local_offset.setter
    def local_offset(self, var):
        """
        Set offset into global array.

        Parameters
        ----------
        var : tuple
        """
        self._local_offset = var

    @property
    def local_array(self):
        """
        The view of the local numpy array.

        Returns
        -------
        local_array : np.ndarray
        """
        return self.view(np.ndarray)

    @property
    def comm(self):
        """
        The communicator over which the array is distributed.

        Returns
        -------
        comm : MPI.Comm
        """
        return self._comm

    @comm.setter
    def comm(self, var):
        """
        Set the communicator over which the array is distributed.

        Parameters
        ----------
        var : MPI.Comm
        """
        self._comm = var

    def __new__(cls, global_shape, axis=0, comm=None, *args, **kwargs):

        # if mpiutil.world is None:
        #     raise RuntimeError('There is no mpi4py installation. Aborting.')

        if comm is None:
            comm = mpiutil.world

        # Determine local section of distributed axis
        local_num, local_start, _ = mpiutil.split_local(global_shape[axis], comm=comm)

        # Figure out the local shape and offset
        lshape = list(global_shape)
        lshape[axis] = local_num

        loffset = [0] * len(global_shape)
        loffset[axis] = local_start

        # Create array
        arr = np.ndarray.__new__(cls, lshape, *args, **kwargs)

        # Set attributes of class
        arr._global_shape = global_shape
        arr._axis = axis
        arr._local_shape = tuple(lshape)
        arr._local_offset = tuple(loffset)
        arr._comm = comm

        return arr

    @property
    def global_slice(self):
        """
        Return an objects that presents a view of the array with global slicing.

        Returns
        -------
        global_slice : object
        """
        return _global_resolver(self)

    @classmethod
    def wrap(cls, array, axis, comm=None):
        """Turn a set of numpy arrays into a distributed MPIArray object.

        This is needed for functions such as `np.fft.fft` which always return
        an `np.ndarray`.

        Parameters
        ----------
        array : np.ndarray
            Array to wrap.
        axis : integer
            Axis over which the array is distributed. The lengths are checked
            to try and ensure this is correct.
        comm : MPI.Comm, optional
            The communicator over which the array is distributed. If `None`
            (default), use `MPI.COMM_WORLD`.

        Returns
        -------
        dist_array : MPIArray
            An MPIArray view of the input.
        """

        # from mpi4py import MPI

        if comm is None:
            comm = mpiutil.world

        # Get axis length, both locally, and globally
        try:
            axlen = array.shape[axis]
        except IndexError as e:
            raise AxisException(
                f"Distributed axis {axis} does not exist in global shape {array.shape}"
            ) from e

        totallen = mpiutil.allreduce(axlen, comm=comm)

        # Figure out what the distributed layout should be
        local_num, local_start, _ = mpiutil.split_local(totallen, comm=comm)

        # Check the local layout is consistent with what we expect, and send
        # result to all ranks.
        layout_issue = mpiutil.allreduce(axlen != local_num, op=mpiutil.MAX, comm=comm)

        if layout_issue:
            raise Exception("Cannot wrap, distributed axis local length is incorrect.")

        # Set shape and offset
        lshape = array.shape
        global_shape = list(lshape)
        global_shape[axis] = totallen

        loffset = [0] * len(lshape)
        loffset[axis] = local_start

        # Setup attributes of class
        dist_arr = array.view(cls)
        dist_arr.global_shape = tuple(global_shape)
        dist_arr.axis = axis
        dist_arr.local_shape = tuple(lshape)
        dist_arr.local_offset = tuple(loffset)
        dist_arr.comm = comm

        return dist_arr

    def redistribute(self, axis):
        """Change the axis that the array is distributed over.

        Parameters
        ----------
        axis : integer
            Axis to distribute over.

        Returns
        -------
        array : MPIArray
            A new copy of the array distributed over the specified axis. Note
            that the local section will have changed.
        """

        # Check to see if this is the current distributed axis
        if self.axis == axis or self.comm is None:
            return self

        # Test to see if the datatype is one understood by MPI, this can
        # probably be fixed up at somepoint by creating a datatype of the right
        # number of bytes
        try:
            mpiutil.typemap(self.dtype)
        except KeyError:
            if self.comm.rank == 0:
                import warnings

                warnings.warn(
                    "Cannot redistribute array of compound datatypes." " Sorry!!"
                )
            return self

        # Get a view of the array
        arr = self.view(np.ndarray)

        if self.comm.size == 1:
            # only one process
            if arr.shape[self.axis] == self.global_shape[self.axis]:
                # We are working on a single node and being asked to do
                # a trivial transpose.
                trans_arr = arr.copy()

            else:
                raise ValueError(
                    "Global shape %s is incompatible with local arrays shape %s"
                    % (self.global_shape, self.shape)
                )
        else:
            pc, _, _ = mpiutil.split_local(arr.shape[axis], comm=self.comm)
            _, sar, ear = mpiutil.split_all(
                self.global_shape[self.axis], comm=self.comm
            )
            _, sac, eac = mpiutil.split_all(arr.shape[axis], comm=self.comm)

            new_shape = np.asarray(self.global_shape)
            new_shape[axis] = pc

            requests_send = []
            requests_recv = []

            trans_arr = np.empty(new_shape, dtype=arr.dtype)
            mpitype = mpiutil.typemap(arr.dtype)
            buffers = list()

            # Cut out the right blocks of the local array to send around
            blocks = np.array_split(arr, np.insert(eac, 0, sac[0]), axis)[1:]

            # Iterate over all processes row wise
            for ir in range(self.comm.size):

                # Iterate over all processes column wise
                for ic in range(self.comm.size):

                    # Construct a unique tag
                    tag = ir * self.comm.size + ic

                    # Send and receive the messages as non-blocking passes
                    if self.comm.rank == ir:
                        # Send the message
                        request = self.comm.Isend(
                            [blocks[ic].flatten(), mpitype], dest=ic, tag=tag
                        )

                        requests_send.append([ir, ic, request])

                    if self.comm.rank == ic:
                        buffer_shape = np.asarray(new_shape)
                        buffer_shape[axis] = eac[ic] - sac[ic]
                        buffer_shape[self.axis] = ear[ir] - sar[ir]
                        buffers.append(np.ndarray(buffer_shape, dtype=arr.dtype))

                        request = self.comm.Irecv(
                            [buffers[ir], mpitype], source=ir, tag=tag
                        )
                        requests_recv.append([ir, ic, request])

            # Wait for all processes to have started their messages
            self.comm.Barrier()

            # For each node iterate over all sends and wait until completion
            for ir, ic, request in requests_send:

                stat = mpiutil.MPI.Status()

                request.Wait(status=stat)

                if stat.error != mpiutil.MPI.SUCCESS:
                    logger.error(
                        f"**** ERROR in MPI SEND (r: {ir} c: {ic} rank: {self.comm.rank}) *****"
                    )

            self.comm.Barrier()

            # For each frequency iterate over all receives and wait until
            # completion
            for ir, ic, request in requests_recv:

                stat = mpiutil.MPI.Status()

                request.Wait(status=stat)

                if stat.error != mpiutil.MPI.SUCCESS:
                    logger.error(
                        f"**** ERROR in MPI RECV (r: {ir} c: {ic} rank: "
                        f"{self.comm.rank}) *****"
                    )

            # Put together the blocks we received
            np.concatenate(buffers, self.axis, trans_arr)

        # Create a new MPIArray object out of the data
        dist_arr = MPIArray(
            self.global_shape, axis=axis, dtype=self.dtype, comm=self.comm
        )
        dist_arr[:] = trans_arr

        return dist_arr

    def enumerate(self, axis):
        """Helper for enumerating over a given axis.

        Parameters
        ----------
        axis : integer
            Which access to enumerate over.

        Returns
        -------
        iterator : (local_index, global_index)
            An enumerator which returns the local index into the array *and*
            the global index it corresponds to.
        """
        start = self.local_offset[axis]
        end = start + self.local_shape[axis]

        return enumerate(range(start, end))

    @classmethod
    def from_hdf5(cls, f, dataset, comm=None, axis=0, sel=None):
        """Read MPIArray from an HDF5 dataset in parallel.

        Parameters
        ----------
        f : filename, or `h5py.File` object
            File to read dataset from.
        dataset : string
            Name of dataset to read from. Must exist.
        comm : MPI.Comm, optional
            MPI communicator to distribute over. If `None` optional, use
            `MPI.COMM_WORLD`.
        axis : int, optional
            Axis over which the read should be distributed. This can be used
            to select the most efficient axis for the reading.
        sel : tuple, optional
            A tuple of slice objects used to make a selection from the array
            *before* reading. The output will be this selection from the dataset
            distributed over the given axis.

        Returns
        -------
        array : MPIArray
        """
        # Don't bother using MPI where the axis is not zero. It's probably just slower.
        # TODO: with tuning this might not be true. Keep an eye on this.
        use_mpi = axis > 0

        # Read the file. Opening with MPI if requested, and we can
        fh = misc.open_h5py_mpi(f, "r", use_mpi=use_mpi, comm=comm)

        dset = fh[dataset]
        dshape = dset.shape  # Shape of the underlying dataset
        naxis = len(dshape)
        dtype = dset.dtype

        # Check that the axis is valid and wrap to an actual position
        if axis < -naxis or axis >= naxis:
            raise AxisException(
                "Distributed axis %i not in range (%i, %i)" % (axis, -naxis, naxis - 1)
            )
        axis = naxis + axis if axis < 0 else axis

        # Ensure sel is defined to cover all axes
        sel = _expand_sel(sel, naxis)

        # Figure out the final array size and create it
        gshape = []
        for l, sl in zip(dshape, sel):
            gshape.append(_len_slice(sl, l))
        dist_arr = cls(gshape, axis=axis, comm=comm, dtype=dtype)

        # Get the local start and end indices
        lstart = dist_arr.local_offset[axis]
        lend = lstart + dist_arr.local_shape[axis]

        # Create the slice object into the dataset by resolving the rank's slice on the
        # sel
        sel[axis] = _reslice(sel[axis], dshape[axis], slice(lstart, lend))
        sel = tuple(sel)

        # Split the axis to get the IO size under ~2GB (only if MPI-IO)
        split_axis, partitions = dist_arr._partition_io(skip=(not fh.is_mpi))

        # Check that there are no null slices, otherwise we need to turn off
        # collective IO to work around an h5py issue (#965)
        no_null_slices = dist_arr.global_shape[axis] >= dist_arr.comm.size

        # Only use collective IO if:
        # - there are no null slices (h5py bug)
        # - we are not distributed over axis=0 as there is no advantage for
        #   collective IO which is usually slow
        # TODO: change if h5py bug fixed
        # TODO: better would be a test on contiguous IO size
        # TODO: do we need collective IO to read chunked data?
        use_collective = fh.is_mpi and no_null_slices and axis > 0

        # Read using collective MPI-IO if specified
        with dset.collective if use_collective else DummyContext():

            # Loop over partitions of the IO and perform them
            for part in partitions:
                islice, fslice = _partition_sel(
                    sel, split_axis, dshape[split_axis], part
                )
                dist_arr[fslice] = dset[islice]

        if fh.opened:
            fh.close()

        return dist_arr

    def to_hdf5(
        self,
        f,
        dataset,
        create=False,
        chunks=None,
        compression=None,
        compression_opts=None,
    ):
        """Parallel write into a contiguous HDF5 dataset.

        Parameters
        ----------
        filename : str, h5py.File or h5py.Group
            File to write dataset into.
        dataset : string
            Name of dataset to write into. Should not exist.
        """

        import h5py

        if not h5py.get_config().mpi:
            if isinstance(f, str):
                self._to_hdf5_serial(f, dataset, create)
                return
            else:
                raise ValueError(
                    "Argument must be a filename if h5py does not have MPI support"
                )

        mode = "a" if create else "r+"

        fh = misc.open_h5py_mpi(f, mode, self.comm)

        start = self.local_offset[self.axis]
        end = start + self.local_shape[self.axis]

        # Construct slices for axis
        sel = ([slice(None, None)] * self.axis) + [slice(start, end)]
        sel = _expand_sel(sel, self.ndim)

        # Check that there are no null slices, otherwise we need to turn off
        # collective IO to work around an h5py issue (#965)
        no_null_slices = self.global_shape[self.axis] >= self.comm.size

        # Split the axis to get the IO size under ~2GB (only if MPI-IO)
        split_axis, partitions = self._partition_io(skip=(not fh.is_mpi))

        # Only use collective IO if:
        # - there are no null slices (h5py bug)
        # - we are not distributed over axis=0 as there is no advantage for
        #   collective IO which is usually slow
        # - unless we want to use compression/chunking
        # TODO: change if h5py bug fixed
        # TODO: better would be a test on contiguous IO size
        use_collective = (
            fh.is_mpi and no_null_slices and (self.axis > 0 or compression is not None)
        )

        if fh.is_mpi and not use_collective:
            # Need to disable compression if we can't use collective IO
            chunks, compression, compression_opts = None, None, None

        dset = fh.create_dataset(
            dataset,
            shape=self.global_shape,
            dtype=self.dtype,
            chunks=chunks,
            compression=compression,
            compression_opts=compression_opts,
        )

        # Read using collective MPI-IO if specified
        with dset.collective if use_collective else DummyContext():

            # Loop over partitions of the IO and perform them
            for part in partitions:
                islice, fslice = _partition_sel(
                    sel, split_axis, self.global_shape[split_axis], part
                )
                dset[islice] = self[fslice]

        if fh.opened:
            fh.close()

    def transpose(self, *axes):
        """Transpose the array axes.

        Parameters
        ----------
        axes : None, tuple of ints, or n ints
            - None or no argument: reverses the order of the axes.
            - tuple of ints: i in the j-th place in the tuple means a’s i-th axis
              becomes a.transpose()’s j-th axis.
            - n ints: same as an n-tuple of the same ints (this form is intended simply
              as a “convenience” alternative to the tuple form)

        Returns
        -------
        array : MPIArray
            Transposed MPIArray as a view of the original data.
        """

        tdata = np.ndarray.transpose(self, *axes)

        if len(axes) == 1 and isinstance(axes[0], (tuple, list)):
            axes = axes[0]
        elif axes is None or axes == ():
            axes = list(range(self.ndim - 1, -1, -1))

        tdata.global_shape = tuple(self.global_shape[ax] for ax in axes)
        tdata.local_shape = tuple(self.local_shape[ax] for ax in axes)
        tdata.local_offset = tuple(self.local_offset[ax] for ax in axes)

        tdata.axis = list(axes).index(self.axis)
        tdata.comm = self._comm

        return tdata

    def reshape(self, *shape):
        """Reshape the array.

        Must not attempt to reshape the distributed axis. That axis must be
        given an input length `None`.

        Parameters
        ----------
        shape : tuple
            Tuple of axis lengths. The distributed must be given `None`.

        Returns
        -------
        array : MPIArray
            Reshaped MPIArray as a view of the original data.
        """

        if len(shape) == 1 and isinstance(shape[0], (tuple, list)):
            shape = tuple(shape[0])

        # Find which axis is distributed
        list_shape = list(shape)
        new_axis = list_shape.index(None)

        # Fill in the missing value
        local_shape = list_shape[:]
        global_shape = list_shape[:]
        local_offset = [0] * len(list_shape)
        local_shape[new_axis] = self.local_shape[self.axis]
        global_shape[new_axis] = self.global_shape[self.axis]
        local_offset[new_axis] = self.local_offset[self.axis]

        # Check that the array sizes are compatible
        if np.prod(local_shape) != np.prod(self.local_shape):
            raise Exception("Dataset shapes incompatible.")

        rdata = np.ndarray.reshape(self, local_shape)

        rdata.axis = new_axis
        rdata.comm = self._comm
        rdata.local_shape = tuple(local_shape)
        rdata.global_shape = tuple(global_shape)
        rdata.local_offset = tuple(local_offset)

        return rdata

    def copy(self):
        """Return a copy of the MPIArray.

        Returns
        -------
        arr_copy : MPIArray
        """
        return MPIArray.wrap(
            self.view(np.ndarray).copy(), axis=self.axis, comm=self.comm
        )

    def gather(self, rank=0):
        """Gather a full copy onto a specific rank.

        Parameters
        ----------
        rank : int, optional
            Rank to gather onto. Default is rank=0

        Returns
        -------
        arr : np.ndarray, or None
            The full global array on the specified rank.
        """
        if self.comm.rank == rank:
            arr = np.ndarray(self.global_shape, dtype=self.dtype)
        else:
            arr = None

        splits = mpiutil.split_all(self.global_shape[self.axis], self.comm)

        for ri, (n, s, e) in enumerate(zip(*splits)):

            if self.comm.rank == rank:

                # Construct a temporary array for the data to be received into
                tshape = list(self.global_shape)
                tshape[self.axis] = n
                tbuf = np.ndarray(tshape, dtype=self.dtype)

                # Set up the non-blocking receive request
                request = self.comm.Irecv(tbuf, source=ri)

            # Send the data
            if self.comm.rank == ri:
                self.comm.Isend(self.view(np.ndarray), dest=rank)

            if self.comm.rank == rank:

                # Wait until the data has arrived
                stat = mpiutil.MPI.Status()
                request.Wait(status=stat)

                if stat.error != mpiutil.MPI.SUCCESS:
                    logger.error(
                        "**** ERROR in MPI RECV (source: %i,  dest rank: %i) *****",
                        ri,
                        rank,
                    )

                # Put the data into the correct location
                dest_slice = [slice(None)] * len(self.shape)
                dest_slice[self.axis] = slice(s, e)
                arr[tuple(dest_slice)] = tbuf

        return arr

    def allgather(self):
        """Gather a full copy onto each rank.

        Returns
        -------
        arr : np.ndarray
            The full global array.
        """
        arr = np.ndarray(self.global_shape, dtype=self.dtype)

        splits = mpiutil.split_all(self.global_shape[self.axis], self.comm)

        for ri, (n, s, e) in enumerate(zip(*splits)):

            # Construct a temporary array for the data to be received into
            tshape = list(self.global_shape)
            tshape[self.axis] = n
            tbuf = np.ndarray(tshape, dtype=self.dtype)

            if self.comm.rank == ri:
                tbuf[:] = self

            self.comm.Bcast(tbuf, root=ri)

            # Copy the array into the correct place
            dest_slice = [slice(None)] * len(self.shape)
            dest_slice[self.axis] = slice(s, e)
            arr[tuple(dest_slice)] = tbuf

        return arr

    def _to_hdf5_serial(self, filename, dataset, create=False):
        """Write into an HDF5 dataset.

        This explicitly serialises the IO so that it works when h5py does not
        support MPI-IO.

        Parameters
        ----------
        filename : str
            File to write dataset into.
        dataset : string
            Name of dataset to write into. Should not exist.
        """

        ## Naive non-parallel implementation to start

        import h5py

        if h5py.get_config().mpi:
            import warnings

            warnings.warn(
                "h5py has parallel support. "
                "Use the parallel `.to_hdf5` routine instead."
            )

        if self.comm is None or self.comm.rank == 0:

            with h5py.File(filename, "a" if create else "r+") as fh:
                if dataset in fh:
                    raise Exception("Dataset should not exist.")

                fh.create_dataset(dataset, self.global_shape, dtype=self.dtype)
                fh[dataset][:] = np.array(0.0).astype(self.dtype)

        # wait until all processes see the created file
        while not os.path.exists(filename):
            time.sleep(1)

        self.comm.Barrier()

        if self.axis == 0:
            dist_arr = self
        else:
            dist_arr = self.redistribute(axis=0)

        size = 1 if self.comm is None else self.comm.size
        for ri in range(size):

            rank = 0 if self.comm is None else self.comm.rank
            if ri == rank:
                with h5py.File(filename, "r+") as fh:

                    start = dist_arr.local_offset[0]
                    end = start + dist_arr.local_shape[0]

                    fh[dataset][start:end] = dist_arr

            dist_arr.comm.Barrier()

    def _partition_io(self, skip=False, threshold=1.99):
        """Split IO of this array into local sections under `threshold`.

        Parameters
        ----------
        skip : bool, optional
            Don't partition, just find and return a full axis.
        threshold : float, optional
            Maximum size of IO (in GB).

        Returns
        -------
        split_axis : int
            Which axis are we going to split along.
        partitions : list of slice objects
            List of slices.
        """
        from mpi4py import MPI

        threshold_bytes = threshold * 2 ** 30
        largest_size = self.comm.allreduce(self.nbytes, op=MPI.MAX)
        num_split = int(np.ceil(largest_size / threshold_bytes))

        # Return early if we can
        if skip or num_split == 1:
            return 0, [slice(0, self.local_shape[0])]

        if self.ndim == 1:
            raise RuntimeError("To parition an array we must have multiple axes.")

        # Try and find the axis to split over
        for split_axis in range(self.ndim):
            if split_axis != self.axis and self.global_shape[split_axis] >= num_split:
                break
        else:
            raise RuntimeError(
                "Can't identify an IO partition less than %.2f GB in size: "
                "shape=%s, distributed axis=%i"
                % (threshold, self.global_shape, self.axis)
            )

        logger.debug("Splitting along axis %i, %i ways", split_axis, num_split)

        # Figure out the start and end of the splits and return
        _, starts, ends = mpiutil.split_m(self.global_shape[split_axis], num_split)

        slices = [slice(start, end) for start, end in zip(starts, ends)]
        return split_axis, slices

    # pylint: disable=inconsistent-return-statements
    # pylint: disable=too-many-branches
    # array_ufunc is a special general function
    # which facilitates the use of a diverse set of ufuncs
    # some which return nothing, and some which return something

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Handles ufunc operations for MPIArray.

        In NumPy, ufuncs are the various fundamental operations applied to
        ndarrays in an element-by-element fashion, such as add() and divide().
        https://numpy.org/doc/stable/reference/ufuncs.html

        ndarray has lots of built-in ufuncs. In order to use them, the MPIArrays
        need to be converted into ndarrays, otherwise NumPy reports a
        NotImplemented error.

        The distributed axis for all input MPIArrays, is expected to be the same.
        Operations across the distributed axis, will not be permitted.

        The new array will either be distributed over that axis, or possibly
        one axis down for `reduce` methods.

        For operations that normally return a scalar, the scalars will be
        wrapped into a 1D array, distributed across axis 0.

        Parameters
        ----------
        ufunc: <function>
            ufunc object that was called
        method: str
            indicates which ufunc method was called.
            one of "__call__", "reduce", "reduceat", "accumulate", "outer", "inner"
        inputs: tuple
            tuple of the input arguments to the ufunc.
            At least one of the inputs is an MPIArray.
        kwargs: dict
            dictionary containing the optional input arguments of the ufunc.
            Important kwargs considered here are 'out' and 'axis'.
        """
        # pylint: disable=no-member
        # known problem with super().__array_ufunc__

        args = []

        # convert all local arrays into ndarrays
        args, dist_axis = _mpi_to_ndarray(inputs)

        if "axis" in kwargs and (kwargs["axis"] == dist_axis):
            raise AxisException(
                f"operations along the distributed axis (in this case, {dist_axis}) "
                "are not allowed."
            )

        # 'out' kwargs contain arrays that the ufunc places the results into
        # this views the local part of the output arrays into an ndarray
        # that the ufunc knows how to work with
        outputs = kwargs.get("out", None)
        if outputs:
            out_args, _ = _mpi_to_ndarray(outputs)
            kwargs["out"] = tuple(out_args)
        else:
            outputs = (None,) * ufunc.nout

        results = super().__array_ufunc__(ufunc, method, *args, **kwargs)

        # that ufunc was not implemented for ndarrays
        if results is NotImplemented:
            return NotImplemented

        # operation was performed in-place, so we can just return
        if method == "at":
            return

        if ufunc.nout == 1:
            results = (results,)

        if "reduce" in method and (
            results[0].shape or getattr(outputs[0], "shape", None)
        ):
            # reduction methods eliminate axes, so the distributed axis
            # might need to be recalculated
            # except when the user explicitly specifies keepdims
            if not kwargs.get("keepdims", False) and (kwargs["axis"] < dist_axis):
                dist_axis -= 1

        ret = []

        for result, output in zip(results, outputs):
            # case: results were placed in the array specified by `out`; return as is
            if output is not None:
                if hasattr(output, "axis") and output.axis != dist_axis:
                    raise AxisException(
                        "provided output MPIArray's distributed axis is not consistent "
                        f"with expected output distributed axis. Expected {dist_axis}; "
                        f"Actual {output.axis}"
                    )
                ret.append(output)
            else:
                # case: the result is an ndarray; wrap it into an MPIArray
                if result.shape:
                    ret.append(MPIArray.wrap(result, axis=dist_axis))
                # case: result is a scalar; convert to 1-d vector, distributed across
                # axis 0
                else:
                    ret.append(MPIArray.wrap(np.reshape(result, (1,)), axis=0))

        return ret[0] if len(ret) == 1 else tuple(ret)

    # pylint: enable=inconsistent-return-statements
    # pylint: enable=too-many-branches

    def __array_finalize__(self, obj):
        """
        Finalizes the creation of the MPIArray, when viewed.

        Note: If you wish to create an MPIArray from an ndarray, please use wrap().
        Do not use ndarray.view(MPIArray).

        In NumPy, ndarrays only go through the `__new__` when being instantiated.
        For views and broadcast, they go through __array_finalize__.
        https://numpy.org/doc/stable/user/basics.subclassing.html#the-role-of-array-finalize

        Parameters
        ----------
        obj : MPIArray, ndarray or None
            The original array being viewed or broadcast.
            When in the middle of a constructor, obj is set to None.
        self : MPIArray or ndarray
            The array which will be created
        """
        if obj is None:
            # we are in the middle of a constructor, and the attributes
            # will be set when we return to it
            return

        if not isinstance(obj, MPIArray):
            # in the middle of an np.ndarray.view() in the wrap()
            return

        # we are in a slice, rebuild the attributes from the original MPIArray
        comm = getattr(obj, "comm", mpiutil.world)

        axis = obj.axis

        # Get local shape
        lshape = self.shape
        global_shape = list(lshape)

        # Obtaining length of distributed axis, without using an mpi.allreduce
        try:
            axlen = obj.global_shape[axis]
        except IndexError as e:
            raise AxisException(
                f"Distributed axis {axis} does not exist in global shape {global_shape}"
            ) from e

        global_shape[axis] = axlen

        # Get offset
        _, local_start, _ = mpiutil.split_local(axlen, comm=comm)

        loffset = [0] * len(lshape)
        loffset[axis] = local_start

        # Setup attributes
        self._global_shape = tuple(global_shape)
        self._axis = axis
        self._local_shape = tuple(lshape)
        self._local_offset = tuple(loffset)
        self._comm = comm
        return


def _partition_sel(sel, split_axis, n, slice_):
    """
    Re-slice a selection along a new axis.

    Take a selection (a tuple of slices) and re-slice along the split_axis (which has
    length n).

    Parameters
    ----------
    sel : Tuple[slice]
        Selection
    split_axis : int
        New split axis
    n : int
        Length of split axis
    slice_

    Returns
    -------
    Tuple[List[slice], Tuple[slice]]
        The new selections for the initial (pre-selection) space and the final
        (post-selection) space.
    """
    # Reconstruct the slice for the split axis
    slice_init = _reslice(sel[split_axis], n, slice_)

    # Construct the final selection
    sel_final = [slice(None)] * len(sel)
    sel_final[split_axis] = slice_

    # Construct the initial selection
    sel_initial = list(sel)
    sel_initial[split_axis] = slice_init

    return tuple(sel_initial), tuple(sel_final)


def _len_slice(slice_, n):
    # Calculate the output length of a slice applied to an axis of length n
    start, stop, step = slice_.indices(n)
    return 1 + (stop - start - 1) // step


def _reslice(slice_, n, subslice):
    # For a slice along an axis of length n, return the slice that would select the
    # slice(start, end) elements of the final array.
    #
    # In other words find a single slice that has the same affect as application of two
    # successive slices
    dstart, dstop, dstep = slice_.indices(n)

    if subslice.step is not None and subslice.step > 1:
        raise ValueError("stride > 1 not supported. subslice: %s" % subslice)

    return slice(
        dstart + subslice.start * dstep,
        min(dstart + subslice.stop * dstep, dstop),
        dstep,
    )


def _expand_sel(sel, naxis):
    # Expand the selection to the full dimensions
    if sel is None:
        sel = [slice(None)] * naxis
    if len(sel) < naxis:
        sel = list(sel) + [slice(None)] * (naxis - len(sel))
    return list(sel)


def _mpi_to_ndarray(inputs):
    """Ensure a list with mixed MPIArrays and ndarrays are all ndarrays.

    Additionally, ensure that all of the MPIArrays are distributed along the same axis.

    Parameters
    ----------
    inputs : list of MPIArrays and ndarrays
        All MPIArrays should be distributed along the same axis.

    Returns
    -------
    args : list of ndarrays
        The ndarrays are built from the local view of inputed MPIArrays.
    dist_axis : int
        The axis that all of the MPIArrays were distributed on.
    """
    args = []
    dist_axis = None

    for array in inputs:
        if isinstance(array, MPIArray):
            if not hasattr(array, 'axis'):
                raise AxisException(
                        "An input to a ufunc has an MPIArray, which is missing its axis property."
                        "If using a lower-case MPI.Comm function, please use its upper-case alternative."
                        "Pickling does not preserve the axis property."
                        "Otherwise, please file an issue on caput with a stacktrace."
                )
            if dist_axis is None:
                dist_axis = array.axis
            else:
                if dist_axis != array.axis:
                    raise AxisException(
                        "The distributed axis for all MPIArrays in an expression "
                        "should be the same"
                    )

            args.append(array.local_array)
        else:
            args.append(array)

    return (args, dist_axis)


class DummyContext:
    """A completely dummy context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class AxisException(Exception):
    """Exception for distributed axes related errors with MPIArrays."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
