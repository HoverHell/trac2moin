#!/usr/bin/env python
# -*- coding: utf-8 -*-

# trac2moin.py
# ----------------------------------------------------------------------------
# Copyright (c) 2012 Colin Guthrie
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software. 
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
# ----------------------------------------------------------------------------

import re
import os
import sys
import shutil
import time
from optparse import OptionParser

parser = OptionParser()
parser.add_option('-t', '--trac', dest='project',
                  help='Path to the Trac project.')
parser.add_option('-n', '--namemap', dest='namemap',
                  help='A file containing a map of oldname|newname.')
parser.add_option('-u', '--usermap', dest='usermap',
                  help='A file containing a map of olduser|newuser.')
parser.add_option('-p', '--prefix', dest='prefix',
                  help='A prefix to give all pages in the new wiki')
parser.add_option('-i', '--inlinefixups', dest='inlinefixups',
                  help='Fix up wiki syntax inline (i.e. each version) rather than with a new revision at the end')
parser.add_option('-o', '--output', dest='output',
                  help='Output path.')

(options, args) = parser.parse_args(sys.argv[1:])

if not 'PYTHON_EGG_CACHE' in os.environ and options.project is not None:
    os.environ['PYTHON_EGG_CACHE'] = os.path.join(options.project, '.egg-cache')

from trac.env import open_environment
from trac.util.text import to_unicode
from trac.util.datefmt import utc

class ConvertWiki:

    def __init__(self, project=options.project, output=options.output, namemapfile=options.namemap, usermapfile=options.usermap, inlinefixups=options.inlinefixups, prefix=options.prefix):
        self.env = open_environment(project)
        if output is None:
          output = "./moin/"

        namemap = {}
        if namemapfile:
          f = open(namemapfile)
          for line in f.readlines():
            line = line.strip()
            if "" == line:
              continue
            (old,new) = line.split("|", 2);
            if new[0] == "-":
              continue
            namemap[old] = new
          f.close()

        usermap = {}
        if usermapfile:
          f = open(usermapfile)
          for line in f.readlines():
            line = line.strip()
            if "" == line:
              continue
            (old,new) = line.split("|", 2);
            if new[0] == "-":
              continue
            usermap[old] = new
          f.close()

        def lookupname(name, label = "Converting"):
          name = "%s" % name
          newname = name

          if not namemap.has_key(name):
            print "%s '%s': Skipping - not in name map" % (label, name)
            return None
          newname = namemap[name]

          if (prefix):
            newname = "%s%s" % (prefix, newname)
          if newname != name:
            print "%s: '%s' to '%s'" % (label, name, newname)
          else:
            print "%s: '%s'" % (label, name)

          return newname

        def translateuser(user):
          if usermap.has_key(user):
            return usermap[user]
          return user

        def moinname(name):
          return re.sub("-", "(2d)", re.sub("/", "(2f)", name))


        def writelog(pagedir, timestamp, rev, pagename, ipnr, author, comment, filename=None):
          lines=[]
          filename=os.path.join(pagedir, "edit-log")
          if os.path.exists(filename):
            f = open(filename, "r")
            lines = f.readlines()
            f.close()

          if filename is None:
            lines.append("%d000000\t%08d\tSAVE\t%s\t%s\t%s\t%s\n" % (timestamp, rev, pagename, ipnr, author, comment))
          else:
            lines.append("%d000000\t%08d\tATTNEW\t%s\t%s\t%s\t%s\t%s\n" % (timestamp, rev, pagename, ipnr, author, comment, filename))
          lines.sort()
          f = open(filename, "w")
          f.write("".join(lines))
          f.close()


        def fixupsyntax(content):
          # Fixup the links first
          content = re.sub("\\[wiki:([^\\] ]+) ([^\\]]+)\\]", "[[\\1|\\2]]", content)
          content = re.sub("\\[wiki:([^\\] ]+)\\]", "[[\\1]]", content)
          content = re.sub("\\[(https?://[^\\] ]+) ([^\\]]+)\\]", "[[\\1|\\2]]", content)
          content = re.sub("\\[(#[^\\] ]+) ([^\\]]+)\\]", "[[\\1|\\2]]", content)

          # Now deal with name map
          for old,new in namemap.items():
            content = re.sub("\\[\\[%s\\]\\]" % old, "[[%s%s|%s]]" % (prefix, new, old), content)
            content = re.sub("\\[\\[%s\\|([^\\]]+)\\]\\]" % old, "[[%s%s|\\1]]" % (prefix, new), content)
            # NB The two below should be combinable with the two above, but python regex
            # Is annoying: http://bugs.python.org/issue1519638
            content = re.sub("\\[\\[%s(#[A-Za-z0-9_]+)\\]\\]" % old, "[[%s%s\\1|%s]]" % (prefix, new, old), content)
            content = re.sub("\\[\\[%s(#[A-Za-z0-9_]+)\\|([^\\]]+)\\]\\]" % old, "[[%s%s\\1|\\2]]" % (prefix, new), content)

            # Need to translate automatic links...
            if "/" in old or re.match("^[A-Z][a-z]+[A-Z]", old):
              content = re.sub("([^A-Za-z0-9/])%s([^A-Za-z0-9/])" % old, "\\1%s%s\\2" % (prefix, new), content)

            # And give them a proper name
            prettyold = re.sub("^ ", "", re.sub("([A-Z])", " \\1", re.sub("/", " → ", old)))
            if "/" in new:
              content = re.sub("([^\\[])%s%s([^A-Za-z0-9/])" % (prefix, new), "\\1[[%s%s|%s]]\\2" % (prefix, new, prettyold), content)

            # Some macros include content... try and deal with these.
            content = re.sub("(\\[(TracNav|TracInclude|Include)\\()%s\\)\\]" % old, "\\1%s%s)]" % (prefix, new), content)

          # And some other general purpose fixups
          content = re.sub("\\[\\[Image\\(([^\\\\)]+)\\)\\]\\]", "{{attachment:\\1}}", content)
          content = re.sub("\\[\\[PageOutline\\]\\]", "<<TableOfContents>>", content)
          content = re.sub("\\[\\[PageOutline\\([0-9]+-([0-9]+)[^\\)]*\\)\\]\\]", "<<TableOfContents(\\1)>>", content)
          content = re.sub("\\[\\[PageOutline\\(([0-9]+)[^\\)]*\\)\\]\\]", "<<TableOfContents(\\1)>>", content)
          content = re.sub("\\[\\[BR\\]\\]", "<<BR>>", content)
          content = re.sub("\\[\\[TracNav\\(([^\\)]+)\\)\\]\\]", "<<Include(\\1)>>", content)
          return content

        db = self.env.get_db_cnx()

        cursor = db.cursor()
        cursor.execute("SELECT name "
                       "FROM wiki "
                       "WHERE author != %s "
                       "GROUP BY name", ('trac',))

        for name in cursor:
          name = "%s" % name
          newname = lookupname(name)
          if newname is None:
            continue

          cursor2 = db.cursor()
          cursor2.execute("SELECT version,text,time,author,ipnr,comment "
                          "FROM wiki "
                          "WHERE name = %s "
                          "ORDER BY version ASC", (name,))

          pagename = moinname(newname)
          pagedir = os.path.join(output, pagename)
          revisionsdir = os.path.join(pagedir, "revisions")
          if not os.path.exists(revisionsdir):
            os.makedirs(revisionsdir)

          i = 0
          content=""
          for version,text,edittime,author,ipnr,comment in cursor2:
            i=i+1
            print "  Version %s by %s (%s)" % (version, author, translateuser(author))
            content = str(text.encode("utf-8"))

            if inlinefixups:
              content = fixupsyntax(content)

            f = open(os.path.join(pagedir, "current"), "w")
            f.write("%08d\n" % i)
            f.close()

            f = open(os.path.join(revisionsdir, "%08d" % i), "w")
            f.write(content)
            f.write("\n")
            f.close()

            writelog(pagedir, int(edittime), i, pagename, ipnr, translateuser(author), comment)

          if not inlinefixups and i > 0:
            i=i+1
            print "  Fixing Syntax %s" % i

            content = fixupsyntax(content)

            f = open(os.path.join(pagedir, "current"), "w")
            f.write("%08d\n" % i)
            f.close()

            f = open(os.path.join(revisionsdir, "%08d" % i), "w")
            f.write(content)
            f.write("\n")
            f.close()
            
            writelog(pagedir, time.time(), i, pagename, "127.0.0.1", "coling", "Fix wiki syntax after Trac import")

          cursor2.close()
        cursor.close()


        cursor = db.cursor()
        cursor.execute("SELECT id,filename,time,author,ipnr "
                       "FROM attachment "
                       "WHERE author != %s "
                       "ORDER BY time ASC", ('trac',))

        for name,filename,uploadtime,author,ipnr in cursor:
          name = "%s" % name
          if re.match("^[0-9]+$", name):
            continue
          newname = lookupname(name, "Converting Attachment '%s'" % filename)
          if newname is None:
            continue
          
          pagedir = os.path.join(output, moinname(newname))
          revisionsdir = os.path.join(pagedir, "revisions")
          if not os.path.exists(revisionsdir):
            os.makedirs(revisionsdir)
          attachmentsdir = os.path.join(pagedir, "attachments")
          if not os.path.exists(attachmentsdir):
            os.makedirs(attachmentsdir)

          shutil.copy(os.path.join(project, "attachments", "wiki", name, filename), os.path.join(attachmentsdir, filename))
          writelog(pagedir, int(uploadtime), 99999999, moinname(newname), ipnr, translateuser(author), "", filename)


if __name__ == "__main__":
    if len(sys.argv) < 3 or options.project is None:
        print "For usage: %s --help" % (sys.argv[0])
        print
    else:
        ConvertWiki()
