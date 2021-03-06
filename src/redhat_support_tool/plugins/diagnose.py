# -*- coding: utf-8 -*-

#
# Copyright (c) 2012 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#           http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from collections import deque
from redhat_support_lib.infrastructure.errors import RequestError, \
    ConnectionError
from redhat_support_tool.helpers.confighelper import EmptyValueError, _
from redhat_support_tool.helpers.constants import Constants
from redhat_support_tool.helpers.launchhelper import LaunchHelper
from redhat_support_tool.plugins import InteractivePlugin, ObjectDisplayOption
from redhat_support_tool.plugins.kb import Kb
from urlparse import urlparse
import os
import pydoc
import redhat_support_tool.helpers.apihelper as apihelper
import redhat_support_tool.helpers.common as common
import tempfile
import logging
import re

__author__ = 'Keith Robertson <kroberts@redhat.com>'
__author__ = 'Spenser Shumaker <sshumake@redhat.com>'
logger = logging.getLogger("redhat_support_tool.plugins.diagnose")


class Diagnose(InteractivePlugin):
    plugin_name = 'diagnose'
    ALL = _("Diagnose a problem")
    _submenu_opts = None
    _sections = None
    _pAry = None

    @classmethod
    def get_usage(cls):
        '''
        The usage statement that will be printed by OptionParser.

        Example:
            - %prog -c CASENUMBER [options] <comment text here>
        Important: %prog is a OptionParser built-in.  Use it!
        '''
        return _('%prog <keywords, file, or directory containing log files>')

    @classmethod
    def get_desc(cls):
        '''
        The description statement that will be printed by OptionParser.

        Example:
            - 'Use the \'%s\' command to add a comment to a case.'\
             % cls.plugin_name
        '''
        return _('Use the \'%s\' command to send a file, a directory '
                 'containing files, or plain text to Shadowman for '
                 'analysis.') % cls.plugin_name

    @classmethod
    def get_epilog(cls):
        '''
        The epilog string that will be printed by OptionParser.  Usually
        used to print an example of how to use the program.

        Example:
         Examples:
          - %s -c 12345678 Lorem ipsum dolor sit amet, consectetur adipisicing
          - %s -c 12345678
        '''
        return _("Examples:\n"
                 "- %s /var/log/jbossas/rhevm-slimmed/boot.log\n"
                 "- %s /var/spool/abrt/ccpp-2012-09-28-09:53:26-4080\n"
                 "- %s /var/log/messages\n"
                 "- %s libvirt error code: 1, message: internal error HTTP "
                 "response code 404\n") % \
                 (cls.plugin_name, cls.plugin_name,
                  cls.plugin_name, cls.plugin_name)

    def get_intro_text(self):
        return _('\nType the number of the solution to view or \'e\' '
                 'to return to the previous menu.')

    def get_prompt_text(self):
        return _('Select a Solution: ')

    def get_sub_menu_options(self):
        return self._submenu_opts

    def _check_input(self):
        msg = _("ERROR: %s requires a file, directory, or text.")\
                    % self.plugin_name

        if not self._line:
            if common.is_interactive():
                userinput = []
                try:
                    print _('Please provide the file, directory, or text '
                            'to be analyzed: Ctrl-d on an empty line to '
                            'submit:')
                    while True:
                        userinput.append(raw_input())
                except EOFError:
                    # User pressed Ctrl-d
                    self._line = str('\n'.join(userinput)).strip().decode(
                                                                    'utf-8')
            else:
                print msg
                raise Exception(msg)

    def insert_obj(self, symptom):
        '''
        Allow insertion of a package object by launchhelper (when selecting
        from the list generated by list_kerneldebugs.py)
        '''
        # Expand yumdict into our YumDownloadHelper and package
        self._line = symptom

    def validate_args(self):
        # Check for required arguments.
        self._check_input()

    def postinit(self):
        self._submenu_opts = deque()
        self._sections = {}
        api = None

        try:
            api = apihelper.get_api()
            if not os.path.isfile(self._line):
                self._pAry = api.problems.diagnoseStr(self._line)
            else:
                report_file = os.path.expanduser(self._line)
                self._pAry = api.problems.diagnoseFile(report_file)

            if len(self._pAry) > 0:
                if not self._parse_problem():
                    raise Exception()
            else:
                raise Exception()
        except EmptyValueError, eve:
            msg = _('ERROR: %s') % str(eve)
            print msg
            logger.log(logging.WARNING, msg)
            raise
        except RequestError, re:
            msg = _('Unable to connect to support services API. '
                    'Reason: %s') % re.reason
            print msg
            logger.log(logging.WARNING, msg)
            raise
        except ConnectionError:
            msg = _('Problem connecting to the support services '
                    'API.  Is the service accessible from this host?')
            print msg
            logger.log(logging.WARNING, msg)
            raise
        except Exception:
            msg = _("Unable to find solutions to %s") % self._line
            print msg
            logger.log(logging.WARNING, msg)
            raise

    def non_interactive_action(self):
        doc = u''
        for opt in self._submenu_opts:
            if opt.display_text != self.ALL:
                doc += self._sections[opt]
        if doc != u'':
            try:
                print doc.encode("UTF-8", 'replace')
            # pylint: disable=W0703
            except Exception, e:
                # There are some truly bizarre errors when you pipe
                # the output from python's 'print' function with sys encoding
                # set to ascii. These errors seem to manifes when you pipe
                # to something like 'more' or 'less'.  You'll get encoding
                # errors. Curiously, you don't see them with 'grep' or
                # even simply piping to terminal.  WTF :(
                logger.log(logging.WARNING, e)
                import sys
                print doc.encode(sys.getdefaultencoding(),
                                 'replace')

    def interactive_action(self, display_option=None):
        if display_option.display_text == self.ALL:
            doc = u''
            for opt in self._submenu_opts:
                if opt.display_text != self.ALL:
                    doc += self._sections[opt]
            pydoc.pipepager(doc.encode("UTF-8", 'replace'),
                            cmd='less -R')
        else:
            sol_id = display_option.stored_obj
            lh = LaunchHelper(Kb)
            lh.run(sol_id)

    def _parse_problem(self,):
        '''
        Use this for non-interactive display of results.aAry
        '''
        # There can be duplicates in the problem array.
        # Remove them in the simplest way possible that works
        # in 2.4, 2.7, etc...
        solutions = set()

        def comparison(newsol, oldsol):
            newid = os.path.basename(newsol.get_uri())
            oldid = os.path.basename(oldsol.get_uri())
            if newid == oldid:
                return True
            else:
                return False

        try:
            for prob in self._pAry:
                links = prob.get_link()
                for link in links:
                    if len(solutions) == 0:
                        solutions.add(link)
                    else:
                        duplicate = False
                        for li in solutions:
                            if comparison(link, li):
                                duplicate = True
                                break
                        if not duplicate:
                            solutions.add(link)

            doc = u''
            for link in solutions:
                doc = u''
                parsed = urlparse(link.get_uri())
                sol_id = os.path.basename(parsed[2])
                doc += '%-8s %-70s\n' % (Constants.ID, sol_id)
                doc += '%-8s %-70s\n' % ('%s:' % Constants.TITLE,
                                           link.get_value())
                doc += '%-8s %-70s' % (Constants.URL,
                                       re.sub("api\.|/rs","", link.get_uri()))
                doc += '\n\n%s%s%s\n\n' % (Constants.BOLD,
                                           str('-' * Constants.MAX_RULE),
                                           Constants.END)

                disp_opt_text = '[%7s] %s' % (sol_id, link.get_value())
                disp_opt = ObjectDisplayOption(disp_opt_text,
                                               'interactive_action',
                                               sol_id)
                self._submenu_opts.append(disp_opt)
                self._sections[disp_opt] = doc
                #disp_opt = DisplayOption('[' + os.path.basename(parsed[2]) +
                #                         ']  ' + link.get_value(),
                #                         'interactive_action')
                #self._submenu_opts.append(disp_opt)
                #self._sections[disp_opt] = doc
        # pylint: disable=W0703
        except Exception, e:
            msg = _('ERROR: problem parsing the attachments.')
            print msg
            logger.log(logging.WARNING, msg)
            logger.log(logging.WARNING, e)
            return False
        if(disp_opt):
            return True
        return False
