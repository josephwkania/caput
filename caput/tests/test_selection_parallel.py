"""Parallel version of the selection tests.

Needs to be run on 1, 2 or 4 MPI processes.
"""

from mpi4py import MPI
import numpy as np
import pytest

from caput import mpiutil, mpiarray, fileformats
from caput.memh5 import MemGroup
from caput.tests.conftest import rm_all_files


comm = MPI.COMM_WORLD


@pytest.fixture
def h5_file_select_parallel(datasets, h5_file):
    if comm.rank == 0:
        m1 = mpiarray.MPIArray.wrap(datasets[0], axis=0, comm=MPI.COMM_SELF)
        m2 = mpiarray.MPIArray.wrap(datasets[1], axis=0, comm=MPI.COMM_SELF)
        container = MemGroup(distributed=True, comm=MPI.COMM_SELF)
        container.create_dataset("dset1", data=m1, distributed=True)
        container.create_dataset("dset2", data=m2, distributed=True)
        container.to_hdf5(h5_file)

    comm.Barrier()

    yield h5_file, datasets

    comm.Barrier()

    if comm.rank == 0:
        rm_all_files(h5_file)


@pytest.fixture
def zarr_file_select_parallel(datasets, zarr_file):
    if comm.rank == 0:
        m1 = mpiarray.MPIArray.wrap(datasets[0], axis=0, comm=MPI.COMM_SELF)
        m2 = mpiarray.MPIArray.wrap(datasets[1], axis=0, comm=MPI.COMM_SELF)
        container = MemGroup(distributed=True, comm=MPI.COMM_SELF)
        container.create_dataset("dset1", data=m1, distributed=True)
        container.create_dataset("dset2", data=m2, distributed=True)
        container.to_file(zarr_file, file_format=fileformats.Zarr)

    comm.Barrier()

    yield zarr_file, datasets

    comm.Barrier()

    # tear down
    if comm.rank == 0:
        rm_all_files(zarr_file)


@pytest.mark.parametrize(
    "container_on_disk, file_format",
    [
        (pytest.lazy_fixture("h5_file_select_parallel"), fileformats.HDF5),
        (pytest.lazy_fixture("zarr_file_select_parallel"), fileformats.Zarr),
    ],
)
@pytest.mark.parametrize("fsel", [slice(1, 8, 2), slice(5, 8, 2)])
@pytest.mark.parametrize("isel", [slice(1, 4), slice(5, 8, 2)])
def test_H5FileSelect_distributed(container_on_disk, fsel, isel, file_format):
    """Load H5 into parallel container while down-selecting axes."""

    sel = {"dset1": (fsel, isel, slice(None)), "dset2": (fsel, slice(None))}

    # Tests are designed to run for 1, 2 or 4 processes
    assert 4 % comm.size == 0

    m = MemGroup.from_file(
        container_on_disk[0],
        selections=sel,
        distributed=True,
        comm=comm,
        file_format=file_format,
    )

    d1 = container_on_disk[1][0][(fsel, isel, slice(None))]
    d2 = container_on_disk[1][1][(fsel, slice(None))]

    _, s, e = mpiutil.split_local(d1.shape[0], comm=comm)

    dslice = slice(s, e)

    # For debugging...
    # Need to dereference datasets as this is collective
    # md1 = m["dset1"][:]
    # md2 = m["dset2"][:]
    # for ri in range(comm.size):
    #     if ri == comm.rank:
    #         print(comm.rank)
    #         print(md1.shape, d1.shape, d1[dslice].shape)
    #         print(md1[0, :2, :2] if md1.size else "Empty")
    #         print(d1[dslice][0, :2, :2] if d1[dslice].size else "Empty")
    #         print()
    #     comm.Barrier()

    assert np.all(m["dset1"][:] == d1[dslice])
    assert np.all(m["dset2"][:] == d2[dslice])
