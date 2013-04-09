# -*- coding: utf-8 -*-
#
# Copyright (C) 2011-2013 Alexander Shorin
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#

from decimal import Decimal
from struct import pack, unpack
from types import *
from simpleubjson import NOOP as NOOP_SENTINEL
from simpleubjson.exceptions import (
    EncodeError, MarkerError, EarlyEndOfStreamError
)
from simpleubjson.compat import (
    BytesIO, b, bytes, unicode,
    dict_itemsiterator, dict_keysiterator, dict_valuesiterator
)


NOOP = b('N')
EOS = b('E')
NULL = b('Z')
FALSE = b('F')
TRUE = b('T')
INT8 = b('B')
INT16 = b('i')
INT32 = b('I')
INT64 = b('L')
FLOAT = b('d')
DOUBLE = b('D')
STRING_S = b('s')
STRING_L = b('S')
HIDEF_S = b('h')
HIDEF_L = b('H')
ARRAY_S = b('a')
OBJECT_S = b('o')
ARRAY_L = b('A')
OBJECT_L = b('O')

BOS_A = object()
BOS_O = object()

CONSTANTS = set([NOOP, EOS, NULL, FALSE, TRUE])
NUMBERS = set([INT8, INT16, INT32, INT64, FLOAT, DOUBLE])
STRINGS = set([STRING_S, STRING_L, HIDEF_S, HIDEF_L])
SHORT_OBJ = set([STRING_S, HIDEF_S, ARRAY_S, OBJECT_S])
LARGE_OBJ = set([STRING_L, HIDEF_L, ARRAY_L, OBJECT_L])
STREAMS = set([ARRAY_S, OBJECT_S])
OBJECT_KEYS = set([STRING_S, STRING_L])
FORBIDDEN = set([NOOP, EOS])


__all__ = ['Draft8Decoder', 'Draft8Encoder']


class Draft8Decoder(object):
    """Decoder of UBJSON data to Python object that follows Draft 8
    specification rules with next data mapping:

    +--------+----------------------------+----------------------------+-------+
    | Marker | UBJSON type                | Python type                | Notes |
    +========+============================+============================+=======+
    | ``N``  | noop                       | :const:`~simpleubjson.NOOP`| \(1)  |
    +--------+----------------------------+----------------------------+-------+
    | ``Z``  | null                       | None                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``F``  | false                      | bool                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``T``  | true                       | bool                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``B``  | byte                       | int                        |       |
    +--------+----------------------------+----------------------------+-------+
    | ``i``  | int16                      | int                        |       |
    +--------+----------------------------+----------------------------+-------+
    | ``I``  | int32                      | int                        |       |
    +--------+----------------------------+----------------------------+-------+
    | ``L``  | int64                      | long                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``d``  | float                      | float                      |       |
    +--------+----------------------------+----------------------------+-------+
    | ``D``  | double                     | float                      |       |
    +--------+----------------------------+----------------------------+-------+
    | ``h``  | hugeint - 2 bytes          | decimal.Decimal            |       |
    +--------+----------------------------+----------------------------+-------+
    | ``H``  | hugeint - 5 bytes          | decimal.Decimal            |       |
    +--------+----------------------------+----------------------------+-------+
    | ``s``  | string - 2 bytes           | unicode                    |       |
    +--------+----------------------------+----------------------------+-------+
    | ``S``  | string - 5 bytes           | unicode                    |       |
    +--------+----------------------------+----------------------------+-------+
    | ``a``  | array - 2 bytes            | list                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``a``  | array - unsized            | generator                  | \(2)  |
    +--------+----------------------------+----------------------------+-------+
    | ``A``  | array - 5 bytes            | list                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``o``  | object - 2 bytes           | dict                       |       |
    +--------+----------------------------+----------------------------+-------+
    | ``o``  | object - unsized           | generator                  | \(3)  |
    +--------+----------------------------+----------------------------+-------+
    | ``O``  | object - 5 bytes           | dict                       |       |
    +--------+----------------------------+----------------------------+-------+

    Notes:

    (1)
        Noop values are ignored by default if only `allow_noop` argument wasn't
        passed as ``True``.

    (2)
        Nested generators are automatically converted to lists.

    (3)
        Unsized objects are represented as list of 2-element tuples with object
        key and value.
    """

    dispatch = {}

    def __init__(self, source, allow_noop=False):
        if isinstance(source, unicode):
            source = source.encode('utf-8')
        if isinstance(source, bytes):
            source = BytesIO(source)
        self.read = source.read
        self.allow_noop = allow_noop
        self.dispatch = self.dispatch.copy()

    def __iter__(self):
        return self

    def next_tlv(self):
        while 1:
            tag = self.read(1)
            if not tag:
                raise EarlyEndOfStreamError('nothing to decode')
            if tag == NOOP and not self.allow_noop:
                continue
            break
        if tag in NUMBERS:
            if tag == INT8:
                # Trivial operations for trivial cases saves a lot of time
                value = ord(self.read(1))
                if value > 128:
                    value -= 256
                    #value, = unpack('>b', self.read(1))
            elif tag == INT16:
                value, = unpack('>h', self.read(2))
            elif tag == INT32:
                value, = unpack('>i', self.read(4))
            elif tag == INT64:
                value, = unpack('>q', self.read(8))
            elif tag == FLOAT:
                value, = unpack('>f', self.read(4))
            elif tag == DOUBLE:
                value, = unpack('>d', self.read(8))
            else:
                assert False, 'tag %r not in NUMBERS %r' % (tag, NUMBERS)
            return tag, None, value
        elif tag in SHORT_OBJ:
            length = ord(self.read(1))
            if tag in STRINGS:
                assert length < 255, 'invalid string length'
                return tag, length, self.read(length)
            return tag, length, None
        elif tag in LARGE_OBJ:
            length, = unpack('>I', self.read(4))
            if tag in STRINGS:
                return tag, length, self.read(length)
            return tag, length, None
        elif tag in CONSTANTS:
            return tag, None, None
        else:
            raise MarkerError('invalid marker 0x%02x (%r)' % (ord(tag), tag))

    def decode_next(self):
        tag, length, value = self.next_tlv()
        return self.dispatch[tag](self, tag, length, value)

    __next__ = next = decode_next

    def decode_noop(self, tag, length, value):
        return NOOP_SENTINEL
    dispatch[NOOP] = decode_noop

    def decode_none(self, tag, length, value):
        return None
    dispatch[NULL] = decode_none

    def decode_false(self, tag, length, value):
        return False
    dispatch[FALSE] = decode_false

    def decode_true(self, tag, length, value):
        return True
    dispatch[TRUE] = decode_true

    def decode_int(self, tag, length, value):
        return value
    dispatch[INT8] = decode_int
    dispatch[INT16] = decode_int
    dispatch[INT32] = decode_int
    dispatch[INT64] = decode_int

    def decode_float(self, tag, length, value):
        return value
    dispatch[FLOAT] = decode_float
    dispatch[DOUBLE] = decode_float

    def decode_string(self, tag, length, value):
        return value.decode('utf-8')
    dispatch[STRING_S] = decode_string
    dispatch[STRING_L] = decode_string

    def decode_hidef(self, tag, length, value):
        return Decimal(value.decode('utf-8'))
    dispatch[HIDEF_S] = decode_hidef
    dispatch[HIDEF_L] = decode_hidef

    def decode_array(self, tag, length, value):
        if tag == ARRAY_S and length == 255:
            return self.decode_array_stream(tag, length, value)
        res = []
        for _ in range(length):
            tag, length, value = self.next_tlv()
            if tag in FORBIDDEN:
                raise MarkerError('invalid marker occurs: %02X' % ord(tag))
            item = self.dispatch[tag](self, tag, length, value)
            if tag in STREAMS and length == 255:
                item = list(item)
            res.append(item)
        return res
    dispatch[ARRAY_S] = decode_array
    dispatch[ARRAY_L] = decode_array

    def decode_object(self, tag, length, value):
        if tag == OBJECT_S and length == 255:
            return self.decode_object_stream(tag, length, value)
        res = {}
        key = None
        for _ in range(length * 2):
            tag, length, value = self.next_tlv()
            if tag in FORBIDDEN:
                raise MarkerError('invalid marker found: %02X' % ord(tag))
            if key is None and tag not in OBJECT_KEYS:
                raise ValueError('key should be string, got %r' % (tag))
            value = self.dispatch[tag](self, tag, length, value)
            if key is None:
                key = value
            else:
                if tag in STREAMS and length == 255:
                    value = list(value)
                res[key] = value
                key = None
        return res
    dispatch[OBJECT_S] = decode_object
    dispatch[OBJECT_L] = decode_object

    def decode_array_stream(self, tag, length, value):
        def array_stream():
            while 1:
                tag, length, value = self.next_tlv()
                if tag == EOS:
                    break
                item = self.dispatch[tag](self, tag, length, value)
                if tag in STREAMS and length == 255:
                    yield list(item)
                else:
                    yield item
        return array_stream()

    def decode_object_stream(self, tag, length, value):
        def object_stream():
            key = None
            while 1:
                tag, length, value = self.next_tlv()
                if tag == NOOP and key is None:
                    yield NOOP_SENTINEL, NOOP_SENTINEL
                elif tag == NOOP and key:
                    continue
                elif tag == EOS:
                    if key:
                        raise EarlyEndOfStreamError(
                            'value missed for key %r' % key)
                    break
                elif key is None and tag not in OBJECT_KEYS:
                    raise ValueError('key should be string')
                else:
                    value = self.dispatch[tag](self, tag, length, value)
                    if key is None:
                        key = value
                    elif tag in STREAMS:
                        yield key, list(value)
                        key = None
                    else:
                        yield key, value
                        key = None
        return object_stream()


class Draft8Encoder(object):
    """Encoder of Python objects into UBJSON data following Draft 8
    specification"""

    dispatch = {}

    def __init__(self, default=None):
        self._default = default or self.default

    def default(self, obj):
        raise EncodeError('unable to encode %r' % obj)

    def encode_next(self, obj):
        tobj = type(obj)
        if tobj in self.dispatch:
            res = self.dispatch[tobj](self, obj)
        else:
            return self.encode_next(self._default(obj))
        if isinstance(res, GeneratorType):
            return bytes().join(res)
        return res

    def encode_noop(self, obj):
        return NOOP
    dispatch[type(NOOP_SENTINEL)] = encode_noop

    def encode_none(self, obj):
        return NULL
    dispatch[NoneType] = encode_none

    def encode_bool(self, obj):
        return [FALSE, TRUE][obj]
    dispatch[BooleanType] = encode_bool

    def encode_int(self, obj):
        if (-2 ** 7) <= obj <= (2 ** 7 - 1):
            return INT8 + chr(obj % 256)
        elif (-2 ** 15) <= obj <= (2 ** 15 - 1):
            marker = INT16
            token = '>h'
        elif (-2 ** 31) <= obj <= (2 ** 31 - 1):
            marker = INT32
            token = '>i'
        elif (-2 ** 63) <= obj <= (2 ** 63 - 1):
            marker = INT64
            token = '>q'
        else:
            return self.encode_decimal(Decimal(obj))
        return marker + pack(token, obj)
    dispatch[IntType] = encode_int
    dispatch[LongType] = encode_int

    def encode_float(self, obj):
        if 1.18e-38 <= abs(obj) <= 3.4e38:
            marker = FLOAT
            token = '>f'
        elif 2.23e-308 <= abs(obj) < 1.8e308:
            marker = DOUBLE
            token = '>d'
        elif obj == float('inf') or obj == float('-inf'):
            return NULL
        else:
            return self.encode_decimal(Decimal(obj))
        return marker + pack(token, obj)
    dispatch[FloatType] = encode_float

    def encode_str(self, obj):
        if isinstance(obj, unicode):
            obj = obj.encode('utf-8')
        length = len(obj)
        if length < 255:
            return STRING_S + chr(length) + obj
        else:
            return STRING_L + INT32 + pack('>i', length) + obj
    dispatch[StringType] = encode_str
    dispatch[UnicodeType] = encode_str

    def encode_decimal(self, obj):
        obj = unicode(obj).encode('utf-8')
        length = len(obj)
        if length < 255:
            return HIDEF_S + chr(length) + obj
        else:
            return HIDEF_L + pack('>i', length) + obj
    dispatch[Decimal] = encode_decimal

    def encode_sequence(self, obj):
        length = len(obj)
        if length < 255:
            marker = ARRAY_S
            size = chr(length)
        else:
            marker = ARRAY_L
            size = pack('>I', length)
        yield marker + size
        for item in obj:
            yield self.encode_next(item)
    dispatch[TupleType] = encode_sequence
    dispatch[ListType] = encode_sequence
    dispatch[set] = encode_sequence
    dispatch[frozenset] = encode_sequence

    def encode_dict(self, obj):
        length = len(obj)
        if length < 255:
            marker = OBJECT_S
            size = chr(length)
        else:
            marker = OBJECT_L
            size = pack('>I', length)
        yield marker + size
        for key, value in obj.items():
            yield self.encode_next(key)
            yield self.encode_next(value)
    dispatch[dict] = encode_dict

    def encode_generator(self, obj):
        yield ARRAY_S + chr(255)
        for item in obj:
            yield self.encode_next(item)
        yield EOS
    dispatch[XRangeType] = encode_generator
    dispatch[GeneratorType] = encode_generator
    dispatch[dict_keysiterator] = encode_generator
    dispatch[dict_valuesiterator] = encode_generator

    def encode_dictitems(self, obj):
        yield OBJECT_S + chr(255)
        for key, value in obj:
            if not isinstance(key, basestring):
                raise EncodeError('invalid object key %r' % key)
            yield self.encode_next(key)
            yield self.encode_next(value)
        yield EOS
    dispatch[dict_itemsiterator] = encode_dictitems