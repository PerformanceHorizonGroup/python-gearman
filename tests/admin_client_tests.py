import unittest

from gearman.admin_client import GearmanAdminClient, ECHO_STRING
from gearman.admin_client_handler import GearmanAdminClientCommandHandler

from gearman.errors import InvalidAdminClientState, ProtocolError
from gearman.protocol import (
    GEARMAN_COMMAND_ECHO_RES,
    GEARMAN_COMMAND_ECHO_REQ,
    GEARMAN_COMMAND_TEXT_COMMAND,
    GEARMAN_SERVER_COMMAND_STATUS,
    GEARMAN_SERVER_COMMAND_VERSION,
    GEARMAN_SERVER_COMMAND_WORKERS,
    GEARMAN_SERVER_COMMAND_MAXQUEUE,
    GEARMAN_SERVER_COMMAND_SHUTDOWN,
    GEARMAN_SERVER_COMMAND_GETPID,
    GEARMAN_SERVER_COMMAND_SHOW_JOBS,
    GEARMAN_SERVER_COMMAND_SHOW_UNIQUE_JOBS,
)

from tests._core_testing import _GearmanAbstractTest, MockGearmanConnectionManager, MockGearmanConnection

class MockGearmanAdminClient(GearmanAdminClient, MockGearmanConnectionManager):
    pass

class CommandHandlerStateMachineTest(_GearmanAbstractTest):
    """Test the public interface a GearmanWorker may need to call in order to update state on a GearmanWorkerCommandHandler"""
    connection_manager_class = MockGearmanAdminClient
    command_handler_class = GearmanAdminClientCommandHandler

    def setUp(self):
        super(CommandHandlerStateMachineTest, self).setUp()
        self.connection_manager.current_connection = self.connection
        self.connection_manager.current_handler = self.command_handler

    def test_send_illegal_server_commands(self):
        self.assertRaises(ProtocolError, self.send_server_command, "This is not a server command")

    def test_ping_server(self):
        self.command_handler.send_echo_request(ECHO_STRING)
        self.assert_sent_command(GEARMAN_COMMAND_ECHO_REQ, data=ECHO_STRING)
        self.assertEqual(self.command_handler._sent_commands[0], GEARMAN_COMMAND_ECHO_REQ)

        self.command_handler.recv_command(GEARMAN_COMMAND_ECHO_RES, data=ECHO_STRING)
        server_response = self.pop_response(GEARMAN_COMMAND_ECHO_REQ)
        self.assertEqual(server_response, ECHO_STRING)

    def test_state_and_protocol_errors_for_status(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_STATUS)

        # Test premature popping as this we aren't until ready we see the '.'
        self.assertRaises(InvalidAdminClientState, self.pop_response, GEARMAN_SERVER_COMMAND_STATUS)

        # Test malformed server status
        self.assertRaises(ProtocolError, self.recv_server_response, b'\t'.join([b'12', b'IP-A', b'CLIENT-A']))

        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_STATUS)
        self.assertEqual(server_response, tuple())

    def test_multiple_status(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_STATUS)
        self.recv_server_response(b'\t'.join([b'test_function', b'1', b'5', b'17']))
        self.recv_server_response(b'\t'.join([b'another_function', b'2', b'4', b'23']))
        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_STATUS)
        self.assertEqual(len(server_response), 2)

        test_response, another_response = server_response
        self.assertEqual(test_response['task'], b'test_function')
        self.assertEqual(test_response['queued'], 1)
        self.assertEqual(test_response['running'], 5)
        self.assertEqual(test_response['workers'],  17)

        self.assertEqual(another_response['task'], b'another_function')
        self.assertEqual(another_response['queued'], 2)
        self.assertEqual(another_response['running'], 4)
        self.assertEqual(another_response['workers'],  23)

    def test_version(self):
        expected_version = '0.12345'

        self.send_server_command(GEARMAN_SERVER_COMMAND_VERSION)
        self.recv_server_response(expected_version)

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_VERSION)
        self.assertEqual(expected_version, server_response)

    def test_state_and_protocol_errors_for_workers(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_WORKERS)

        # Test premature popping as this we aren't until ready we see the '.'
        self.assertRaises(InvalidAdminClientState, self.pop_response, GEARMAN_SERVER_COMMAND_WORKERS)

        # Test malformed responses
        self.assertRaises(ProtocolError, self.recv_server_response, b' '.join([b'12', b'IP-A', b'CLIENT-A']))
        self.assertRaises(ProtocolError, self.recv_server_response, b' '.join([b'12', b'IP-A', b'CLIENT-A', b'NOT:']))

        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_WORKERS)
        self.assertEqual(server_response, tuple())

    def test_multiple_workers(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_WORKERS)
        self.recv_server_response(b' '.join([b'12', b'IP-A', b'CLIENT-A', b':', b'function-A', b'function-B']))
        self.recv_server_response(b' '.join([b'13', b'IP-B', b'CLIENT-B', b':', b'function-C']))
        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_WORKERS)
        self.assertEqual(len(server_response), 2)

        test_response, another_response = server_response
        self.assertEqual(test_response['file_descriptor'], b'12')
        self.assertEqual(test_response['ip'], b'IP-A')
        self.assertEqual(test_response['client_id'], b'CLIENT-A')
        self.assertEqual(test_response['tasks'],  (b'function-A', b'function-B'))

        self.assertEqual(another_response['file_descriptor'], b'13')
        self.assertEqual(another_response['ip'], b'IP-B')
        self.assertEqual(another_response['client_id'], b'CLIENT-B')
        self.assertEqual(another_response['tasks'],  (b'function-C', ))

    def test_maxqueue(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_MAXQUEUE)
        self.assertRaises(ProtocolError, self.recv_server_response, b'NOT OK')

        # Pop prematurely
        self.assertRaises(InvalidAdminClientState, self.pop_response, GEARMAN_SERVER_COMMAND_MAXQUEUE)

        self.recv_server_response(b'OK')
        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_MAXQUEUE)
        self.assertEqual(server_response, b'OK')

    def test_getpid(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_GETPID)

        self.recv_server_response(b'OK')
        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_GETPID)
        self.assertEqual(server_response, b'OK')

    def test_show_jobs(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_SHOW_JOBS)

        self.recv_server_response(b'handle\t1\t1\t1')
        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_SHOW_JOBS)
        self.assertEqual(server_response[0], {
            'handle': b'handle',
            'queued': 1,
            'canceled': 1,
            'enabled': 1,
        })

    def test_show_jobs_invalid(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_SHOW_JOBS)

        self.assertRaises(ProtocolError, self.recv_server_response, b'invalid\tresponse')

    def test_show_unique_jobs(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_SHOW_UNIQUE_JOBS)

        self.recv_server_response(b'handle1,handle2')
        self.recv_server_response(b'.')

        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_SHOW_UNIQUE_JOBS)
        self.assertEqual(server_response[0], {
            'unique': b'handle1,handle2',
        })

    def test_show_unique_jobs_invalid(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_SHOW_UNIQUE_JOBS)

        self.assertRaises(ProtocolError, self.recv_server_response, b'invalid\tresponse')

    def test_shutdown(self):
        self.send_server_command(GEARMAN_SERVER_COMMAND_SHUTDOWN)

        # Pop prematurely
        self.assertRaises(InvalidAdminClientState, self.pop_response, GEARMAN_SERVER_COMMAND_SHUTDOWN)

        self.recv_server_response(None)
        server_response = self.pop_response(GEARMAN_SERVER_COMMAND_SHUTDOWN)
        self.assertEqual(server_response, None)

    def send_server_command(self, expected_command):
        self.command_handler.send_text_command(expected_command)
        expected_line = "%s\n" % expected_command
        self.assert_sent_command(GEARMAN_COMMAND_TEXT_COMMAND, raw_text=expected_line)

        self.assertEqual(self.command_handler._sent_commands[0], expected_command)

    def recv_server_response(self, response_line):
        self.command_handler.recv_command(GEARMAN_COMMAND_TEXT_COMMAND, raw_text=response_line)

    def pop_response(self, expected_command):
        server_cmd, server_response = self.command_handler.pop_response()
        self.assertEqual(expected_command, server_cmd)

        return server_response

if __name__ == '__main__':
    unittest.main()
