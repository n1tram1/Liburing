import socket
import liburing


def test_socket_timeout():
    ring = liburing.io_uring()

    # socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
    server.bind(('0.0.0.0', 0))  # random port
    server.listen(32)

    # prepare
    fd = server.fileno()
    addr = liburing.ffi.new('struct sockaddr *')
    addrlen = liburing.ffi.new('socklen_t *', liburing.ffi.sizeof(addr))
    print()
    try:
        # initialization
        assert liburing.io_uring_queue_init(32, ring, 0) == 0

        # accept
        sqe = liburing.io_uring_get_sqe(ring)
        liburing.io_uring_prep_accept(sqe, fd, addr, addrlen, 0)
        sqe.flags |= liburing.IOSQE_IO_LINK
        sqe.user_data = 1

        sqe = liburing.io_uring_get_sqe(ring)
        ts = liburing.timespec(0, 1000000//24)  # nanosecond
        liburing.io_uring_prep_link_timeout(sqe, ts, 0)
        sqe.user_data = 2

        assert liburing.io_uring_submit(ring) == 2

        while True:
            try:
                cqes = liburing.io_uring_cqes()
                assert liburing.io_uring_peek_cqe(ring, cqes) == 0
            except BlockingIOError:
                print('waiting')
            else:
                cqe = cqes[0]
                if cqe.user_data == 1:
                    # OSError: [Errno 125] Operation canceled
                    assert cqe.res == -125
                    liburing.io_uring_cqe_seen(ring, cqe)
                    continue
                else:
                    # Timeout value confirm
                    assert cqe.user_data == 2

                    # `OSError: [Errno 62] Timer expired` or
                    # `BlockingIOError: [Errno 114] Operation already in progress`
                    assert cqe.res == -62 or -114
                    liburing.io_uring_cqe_seen(ring, cqe)
                    break

    finally:
        server.close()
        liburing.io_uring_queue_exit(ring)
