# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Alexander Shorin
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#

#: Noop sentinel value
NOOP = type('NoopType', (object,), {})()

from cStringIO import StringIO
from simpleubjson.decoder import UBJSONDecoder
from simpleubjson.encoder import UBJSONEncoder

_default_decoder = UBJSONDecoder()
_default_encoder = UBJSONEncoder()

def decode(data, default=None, handlers=None):
    """Decodes input stream of UBJSON data to Python object.

    :param data: `.read([size])`-able object or source string.
    :param default: Callable object that would be used if there is no handlers
                    matched for occurred marker.
                    Takes 3 arguments: decoder instance, marker and data stream.
    :param handlers: Custom set of handlers where key is UBJSON marker and
                     value is any callable that takes decoder instance and
                     data stream. Setting marker handler to None removes support
                     of it.
    :type handlers: dict

    :return: Decoded Python object. See mapping table below.

    :raises:
        ValueError if:
            * Nothing to decode: empty data source.
            * Unsupported marker: probably it's invalid.
            * Unexpected marker: `noop` value or EOS shouldn't occurs in sized
              arrays or objects.
            * Object key is not string type.
    """
    if isinstance(data, basestring):
        data = StringIO(data)
    if default is None and handlers is None:
        return _default_decoder.decode(data)
    kwargs = {
        'default': default,
        'handlers': handlers
    }
    return UBJSONDecoder(**kwargs).decode(data)


def encode(data, output=None):
    """Encodes Python object to Universal Binary JSON data.

    :param data: Python object.
    :param output: `.write([data])`-able object.

    :return: Encoded Python object. See mapping table below.
             If `output` param is specified, all data would be written into it
             by chunks and None will be returned.

    :raises:
        * TypeError if no handlers specified for passed value type.
        * ValueError if unable to pack Python value to binary form.
    """
    return _default_encoder.encode(data, output)
