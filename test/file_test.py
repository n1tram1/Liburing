import os
import ctypes
import liburing


def test_file_registration(tmpdir):
    ring = liburing.io_uring()
    assert liburing.io_uring_queue_init(1, ring, 0) == 0
    fd1 = os.open(os.path.join(tmpdir, '1.txt'), os.O_CREAT)
    fd2 = os.open(os.path.join(tmpdir, '2.txt'), os.O_CREAT)
    try:
        files = liburing.files_fds(fd1, fd2)
        assert liburing.io_uring_register_files(ring, files, len(files)) == 0
        assert liburing.io_uring_unregister_files(ring) == 0
    finally:
        os.close(fd1)
        os.close(fd2)
        liburing.io_uring_queue_exit(ring)


def test_files_write_read_fsync(tmpdir):
    fd = os.open(os.path.join(tmpdir, '1.txt'), os.O_RDWR | os.O_CREAT, 0o660)
    ring = liburing.io_uring()
    cqe = ctypes.POINTER(liburing.io_uring_cqe)  # cqe (completion queue entry)
    # prepare for writing
    vecs_write = liburing.iovec_write(b'hello', b'world')
    # prepare for reading
    hello = bytearray(5)  # buffer holder for reading
    world = bytearray(5)
    vecs_read = liburing.iovec_read(hello, world)
    try:
        # initialization
        assert liburing.io_uring_queue_init(3, ring, 0) == 0

        # write "hello"
        sqe = liburing.io_uring_get_sqe(ring)  # get sqe (submission queue entry) to fill
        liburing.io_uring_prep_writev(sqe, fd, vecs_write[0], 1, 0)

        # write "world"
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_writev(sqe, fd, vecs_write[1], 1, 5)

        # fsync data only
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_fsync(sqe, fd, liburing.IORING_FSYNC_DATASYNC)
        sqe.contents.user_data = 1
        sqe.contents.flags = liburing.IOSQE_IO_DRAIN

        # submit both writes and fsync
        assert liburing.io_uring_submit(ring) == 3

        # wait for cqe (completion queue entry)
        assert liburing.io_uring_wait_cqes(ring, cqe(), 3, None, None) == 0

        # read "hello"
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_readv(sqe, fd, vecs_read[0], 1, 0)

        # read "world"
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_readv(sqe, fd, vecs_read[1], 1, 5)

        # submit both reads
        assert liburing.io_uring_submit(ring) == 2

        # wait for the sqe to complete
        assert liburing.io_uring_wait_cqes(ring, cqe(), 2, None, None) == 0

        # match buffer holders content
        assert hello == b'hello'
        assert world == b'world'
    finally:
        os.close(fd)
        liburing.io_uring_queue_exit(ring)
