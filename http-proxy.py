#!/usr/bin/env python3

import argparse
import datetime
import socket
from urllib.parse import urlparse
from enum import Enum, auto


# Enumeration to represent message types
class MessageType(Enum):
    REQUEST = auto()  # constant values are auto-assigned
    RESPONSE = auto()  # constant values are auto-assigned


def build_message(message):
    # replacing the original version (this is intentional)
    data = ''
    if message['type'] is MessageType.REQUEST:
        message_header = '{} {} {}\r\n'.format(message['method'], message['uri'], 'HTTP/1.0')
    else:
        message_header = '{} {} {}\r\n'.format(message['version'], message['status-code'], message['status-text'])
    data = data + message_header
    for header in message['headers']:
        data = data + '{}: {}\r\n'.format(header['name'], header['value'])  # Format each header properly
    data = data + '\r\n'
    req = data.encode('iso-8859-1')
    if len(message['body']) > 0:
        req = req + message['body']
    return req


# returns the host and port
# run by doing:  h, p = parse_uri(dest)
def parse_uri(uri):
    uri_parts = urlparse(uri)
    scheme = uri_parts.scheme
    host = uri_parts.hostname
    # urlparse can't deal with partial URI's that don't include the
    # protocol, e.g., push.services.mozilla.com:443
    if host:  # correctly parsed
        if uri_parts.port:
            port = uri_parts.port
        else:
            port = socket.getservbyname(scheme)
    else:  # incorrectly parsed
        uri_parts = uri.split(':')
        host = uri_parts[0]
        if len(uri) > 1:
            port = int(uri_parts[1])
        else:
            port = 80
    return host, port


# returns header in dict format
def get_header_response(data):
    params = data.split(":", 1)
    if len(params) != 2:
        return None
    header = {'name': params[0].strip(), 'value': params[1].strip()}
    return header


def parse_line(data, encoding='iso-8859-1'):
    fields = data.partition(b'\n')

    if len(fields[1]) == 0:
        return None, data

    line = fields[0].rstrip(b'\r')
    fin_line = line.decode(encoding)

    if len(fields[2]) == 0:
        return fin_line, None

    return fin_line, fields[2]


# returns a dictionary representation of full message
# returns none if the message is not complete
def parse_message(data, message_type):
    message = {
        'Content-Length': 0,
        'Referer': "-",
        'User-Agent': "-",
        'body': b''
    }
    headers = []
    try:
        line, unparsed = parse_line(data)
        req = line.split(' ', 2)
        if len(req) != 3:
            raise Exception
        message['type'] = message_type
        if message['type'] is MessageType.REQUEST:
            message['method'] = req[0]
            message['uri'] = req[1]
            message['version'] = req[2]
        else:
            message['version'] = req[0]
            message['status-code'] = req[1]
            message['status-text'] = req[2]
        line, unparsed = parse_line(unparsed)
        while line != '':
            if line is None:
                raise Exception
            if len(headers) > 0 and (line.startswith(" ") or line.startswith("\t")):
                last_header = headers[len(headers) - 1]
                last_header['value'] = last_header['value'] + line
            else:
                header = get_header_response(line)
                if header is None:
                    raise Exception
                headers.append(header)
                if header['name'] == 'Content-Length':
                    message['Content-Length'] = int(header['value'])
                if header['name'] == 'Referer':
                    message['Referer'] = header['value']
                if header['name'] == 'User-Agent':
                    message['User-Agent'] = header['value']
            line, unparsed = parse_line(unparsed)
        if message['Content-Length'] > 0:
            length = message['Content-Length']
            if len(unparsed) < length:
                raise Exception
            elif len(unparsed) > length:
                unparsed = unparsed[:length]
                message['body'] = unparsed
            else:
                message['body'] = unparsed
        message['headers'] = headers
        return message, unparsed
    except:
        return None, data


# establishes the connection and appends entire request to buffer
# returns
def get_response(host, port, req):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.connect((host, port))
        # send message
        s.sendall(req)
        # receive response
        buffer = b''
        while True:
            data = s.recv(1024)
            if not data:
                break
            buffer = buffer + data
            message, unparsed = parse_message(buffer, MessageType.RESPONSE)
            if message is not None:
                return build_message(message), message


def main():
    # register arguments 
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, help='TCP port for HTTP proxy', default=9999)

    # parse the command line
    args = parser.parse_args()

    # SET UP SERVER SOCKET
    # Use sockopt to avoid bind() exception: OSError: [Errno 48] Address already in use
    HOST = '127.0.0.1'
    PORT = args.port

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # ACCEPT NEW CONNECTIONS (in a loop / one at a time)
    s.bind((HOST, PORT))
    s.listen()
    while True:
        conn, addr = s.accept()
        # RECEIVE BYTES AND DECODE AS STRING
        buffer = b''
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buffer = buffer + data
            message, unparsed = parse_message(buffer, MessageType.REQUEST)
            if message is not None:
                dest_host, dest_port = parse_uri(message['uri'])
                req = build_message(message)
                response, m_resp = get_response(dest_host, dest_port, req)
                conn.sendall(response)
                req_host = addr[0]
                now = datetime.datetime.now()
                time_stamp = now.strftime('%d/%b/%Y:%H:%M:%S')
                message_header = '\"{} {} {}\"'.format(message['method'], message['uri'], message['version'])
                print("{} {} {} {} {} {} {}\r\n".format(req_host, time_stamp, message_header,
                                                        m_resp['status-code'], m_resp['Content-Length'],
                                                        message['Referer'], message['User-Agent']))
                break


if __name__ == "__main__":
    main()
