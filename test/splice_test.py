import os
import liburing


def test_clone_file_using_splice(tmpdir):
    fd_in = os.open(os.path.join(tmpdir, '1.txt'), os.O_RDWR | os.O_CREAT, 0o660)
    fd_out = os.open(os.path.join(tmpdir, '2.txt'), os.O_RDWR | os.O_CREAT, 0o660)
    flags = liburing.SPLICE_F_MOVE | liburing.SPLICE_F_MORE
    data = b'hello world'
    BUF_SIZE = len(data)
    os.write(fd_in, data)
    r, w = os.pipe()

    ring = liburing.io_uring()
    cqes = liburing.io_uring_cqes(2)

    try:
        # initialization
        assert liburing.io_uring_queue_init(2, ring, 0) == 0

        # read from file "1.txt"
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_splice(sqe, fd_in, 0, w, -1, BUF_SIZE, flags)
        sqe.user_data = 1

        # chain top and bottom sqe
        sqe.flags |= liburing.IOSQE_IO_LINK

        # write to file "2.txt"
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_splice(sqe, r, -1, fd_out, 0, BUF_SIZE, flags)
        sqe.user_data = 2

        # submit both
        assert liburing.io_uring_submit(ring) == 2

        # wait for ``2`` entry to complete using single syscall
        assert liburing.io_uring_wait_cqes(ring, cqes, 2) == 0
        cqe = cqes[0]
        assert cqe.res == BUF_SIZE
        assert cqe.user_data == 1
        liburing.io_uring_cqe_seen(ring, cqe)

        # re-uses the same resources from above?!
        assert liburing.io_uring_wait_cqes(ring, cqes, 2) == 0
        cqe = cqes[0]
        assert cqe.res == BUF_SIZE
        assert cqe.user_data == 2
        liburing.io_uring_cqe_seen(ring, cqe)
        assert os.read(fd_out, BUF_SIZE) == data

    finally:
        os.close(fd_in)
        os.close(fd_out)
        liburing.io_uring_queue_exit(ring)
