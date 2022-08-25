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


class CascadingStyles(object):
    def __init__(self, defaults = None):
        if defaults is None:
            defaults = {}
        self.defaults = defaults
        self.scopes = []


    def appendScope(self,scope=None):
        """Add a new scope for styles"""
        if scope is None:
            scope = {}
        self.scopes.append(scope)

    def popScope(self):
        """remove the most recent scope of styles"""
        return self.scopes.pop(-1)

    def __getitem__(self, k):
        """get the current setting for the style"""
        for scope in self.scopes[::-1]:
            if scope.get(k) is not None:
                return scope[k]

        if self.defaults.get(k) is not None:
            return self.defaults[k]
        else:
            raise KeyError(str(k))


    def __setitem__(self, k, v):
        """Set a style in the current scope"""
        self.scopes[-1][k] = v

    def __str__(self):
        style = self.currentStyle()
        return ";".join(["%s:%s"%(k,v) for (k,v) in style.items()])

    def currentStyle(self):
        """return all styles applied at this point"""
        styles = {}
        for scope in self.scopes:
            styles.update(scope)

        for key,v in self.defaults.items():
            if styles.get(key,None) == v:
                del styles[key]
        return styles

    def scopeStyle(self):
        """return the styles of this scope only"""
        one_scope = CascadingStyles(defaults = self.defaults)
        one_scope.appendScope(self.scopes[-1])
        return one_scope
