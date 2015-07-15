# -*- coding: utf-8 -*-
##############################################################################
#
#    This module copyright (C) 2015 Therp BV (<http://therp.nl>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import models, tools
from .ir_rule import SUSPEND_CONTEXT_KEY


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @tools.ormcache_context(accepted_keys=('lang', SUSPEND_CONTEXT_KEY))
    def check(self, cr, uid, model, mode='read', raise_exception=True,
              context=None):
        if context and context.get(SUSPEND_CONTEXT_KEY):
            return True
        return super(IrModelAccess, self).check(
            cr, uid, model, mode=mode, raise_exception=raise_exception,
            context=context)
