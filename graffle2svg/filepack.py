#!/usr/bin/env python3
#Copyright (c) 2009, Tim Wintle
#Copyright (c) 2015, Tim Wintle, Stephane Galland
#All rights reserved.
#
#Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#    * Neither the name of the project nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import gzip
from urllib.request import urlopen

import chardet  # https://pypi.org/project/chardet/


class GraffleFilePack:
    __file = None

    def __init__(self, fn):
        if not fn:
            raise Exception('You must specify an input file')
        elif self.detectGZipXMLFile(fn):
            self.__file = gzip.open(fn, 'rb')
        elif self.detectXMLFile(fn):
            self.__file = open(fn, 'rb')
        else:
            raise Exception(f'Invalid input file: {fn}')

    @property
    def fileObject(self):
        return self.__file

    def read(self):
        return self.__file.read()

    def close(self):
        self.__file.close()

    def detectGZipXMLFile(self, fn):
        """Is this a zipped xml file?"""
        result = False
        try:
            f = gzip.open(fn, 'rb')
            try:
                byteString = f.readline()
                result = (byteString and byteString[:5] == b'<?xml')
            except:
                result = False
            f.close()
        except:
            pass
        return result

    def detectXMLFile(self, fn):
        """Is this an xml file?"""
        result = False
        encoding = self.__detect_encoding(fn)
        if encoding and encoding['encoding']:
            encoding = encoding['encoding']
            try:
                f = open(fn, 'r', encoding=encoding)
                try:
                    string = f.readline()
                    result = (string and string[:5] == '<?xml')
                except:
                    result = False
                f.close()
            except:
                pass
        return result

    def __detect_encoding(self, fn):
        fh = urlopen(f'file:{fn}')
        result = chardet.detect(fh.read())
        fh.close()
        return result


if __name__ == '__main__':
    gfp = GraffleFilePack('gziptest.graffle')
    print(gfp.read())
