# Copyright: Damien Elmes <anki@ichi2.net>
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from aqt.qt import *
import re
from anki.consts import *
import aqt
from anki.sound import playFromText, clearAudioQueue
from aqt.utils import saveGeom, restoreGeom, getBase, mungeQA, \
     saveSplitter, restoreSplitter, showInfo, askUser, getOnlyText, \
     showWarning, openHelp
from anki.utils import isMac, isWin

#        raise Exception("Remember to disallow media&latex refs in edit.")

class CardLayout(QDialog):

    def __init__(self, mw, note, ord=0, parent=None):
        QDialog.__init__(self, parent or mw, Qt.Window)
        self.mw = aqt.mw
        self.parent = parent or mw
        self.note = note
        self.ord = ord
        self.col = self.mw.col
        self.mm = self.mw.col.models
        self.model = note.model()
        self.setupTabs()
        self.setupButtons()
        self.setWindowTitle(_("%s Layout") % self.model['name'])
        v1 = QVBoxLayout()
        v1.addWidget(self.tabs)
        v1.addLayout(self.buttons)
        self.setLayout(v1)
        self.mw.checkpoint(_("Card Layout"))
        self.redraw()
        restoreGeom(self, "CardLayout")
        self.exec_()

    def redraw(self):
        self.cards = self.col.previewCards(self.note, 2)
        self.redrawing = True
        self.updateTabs()
        self.redrawing = False
        self.selectCard(self.ord)

    def setupTabs(self):
        c = self.connect
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setUsesScrollButtons(True)
        add = QPushButton("+")
        add.setFixedWidth(30)
        c(add, SIGNAL("clicked()"), self.onAddCard)
        self.tabs.setCornerWidget(add)
        c(self.tabs, SIGNAL("currentChanged(int)"), self.selectCard)
        c(self.tabs, SIGNAL("tabCloseRequested(int)"), self.onRemoveTab)

    def updateTabs(self):
        self.forms = []
        self.tabs.clear()
        for t in self.model['tmpls']:
            self.addTab(t)

    def addTab(self, t):
        c = self.connect
        w = QWidget()
        l = QHBoxLayout()
        l.setMargin(0)
        l.setSpacing(3)
        left = QWidget()
        # template area
        tform = aqt.forms.template.Ui_Form()
        tform.setupUi(left)
        c(tform.front, SIGNAL("textChanged()"), self.saveCard)
        c(tform.back, SIGNAL("textChanged()"), self.saveCard)
        l.addWidget(left, 5)
        # preview area
        right = QWidget()
        pform = aqt.forms.preview.Ui_Form()
        pform.setupUi(right)
        def linkClicked(url):
            QDesktopServices.openUrl(QUrl(url))
        for wig in pform.front, pform.back:
            wig.page().setLinkDelegationPolicy(
                QWebPage.DelegateExternalLinks)
            c(wig, SIGNAL("linkClicked(QUrl)"), linkClicked)
        l.addWidget(right, 5)
        w.setLayout(l)
        self.forms.append({'tform': tform, 'pform': pform})
        self.tabs.addTab(w, t['name'])

    def onRemoveTab(self, idx):
        if not self.mm.remTemplate(self.model, self.cards[idx].template()):
            return showWarning(_("""\
Removing this card would cause one or more notes to be deleted. \
Please create a new card first."""))
        self.redraw()

    # Buttons
    ##########################################################################

    def setupButtons(self):
        c = self.connect
        l = self.buttons = QHBoxLayout()
        help = QPushButton(_("Help"))
        help.setAutoDefault(False)
        l.addWidget(help)
        c(help, SIGNAL("clicked()"), self.onHelp)
        l.addStretch()
        rename = QPushButton(_("Rename"))
        rename.setAutoDefault(False)
        l.addWidget(rename)
        c(rename, SIGNAL("clicked()"), self.onRename)
        repos = QPushButton(_("Reposition"))
        repos.setAutoDefault(False)
        l.addWidget(repos)
        c(repos, SIGNAL("clicked()"), self.onReorder)
        l.addStretch()
        close = QPushButton(_("Close"))
        close.setAutoDefault(False)
        l.addWidget(close)
        c(close, SIGNAL("clicked()"), self.accept)

    # Cards
    ##########################################################################

    def selectCard(self, idx):
        if self.redrawing:
            return
        self.ord = idx
        self.card = self.cards[idx]
        self.tab = self.forms[idx]
        self.tabs.setCurrentIndex(idx)
        self.readCard()
        self.renderPreview()

    def readCard(self):
        t = self.card.template()
        self.redrawing = True
        self.tab['tform'].front.setPlainText(t['qfmt'])
        self.tab['tform'].back.setPlainText(t['afmt'])
        self.redrawing = False

    def saveCard(self):
        if self.redrawing:
            return
        text = self.tab['tform'].front.toPlainText()
        self.card.template()['qfmt'] = text
        text = self.tab['tform'].back.toPlainText()
        self.card.template()['afmt'] = text
        self.renderPreview()

    # Preview
    ##########################################################################

    def renderPreview(self):
        c = self.card
        styles = "\n.cloze { font-weight: bold; color: blue; }"
        html = '''<html><head>%s</head><body id=card>
<style>%s</style>%s</body></html>'''
        ti = self.maybeTextInput
        base = getBase(self.mw.col)
        self.tab['pform'].front.setHtml(
            html % (base, styles, ti(mungeQA(c.q(reload=True)))))
        self.tab['pform'].back.setHtml(
            html % (base, styles, ti(mungeQA(c.a()), 'a')))

    def maybeTextInput(self, txt, type='q'):
        if type == 'q':
            repl = "<center><input type=text value='%s'></center>" % _(
                "(text is typed in here)")
        else:
            repl = _("(typing comparison appears here)")
        return re.sub("\[\[type:.+?\]\]", repl, txt)

    # Card operations
    ######################################################################

    def onRename(self):
        name = getOnlyText(_("New name:"),
                           default=self.card.template()['name'])
        if not name:
            return
        if name in [c.template()['name'] for c in self.cards
                    if c.template()['ord'] != self.ord]:
            return showWarning(_("That name is already used."))
        self.card.template()['name'] = name
        self.tabs.setTabText(self.tabs.currentIndex(), name)

    def onReorder(self):
        n = len(self.cards)
        cur = self.card.template()['ord']+1
        pos = getOnlyText(
            _("Enter new card position (1...%s):") % n,
            default=str(cur))
        if not pos:
            return
        try:
            pos = int(pos)
        except ValueError:
            return
        if pos < 1 or pos > n:
            return
        if pos == cur:
            return
        pos -= 1
        self.mm.moveTemplate(self.model, self.card.template(), pos)
        self.ord = pos
        self.redraw()

    def onAddCard(self):
        name = getOnlyText(_("Name:"))
        if not name:
            return
        if name in [c.template()['name'] for c in self.cards]:
            return showWarning(_("That name is already used."))
        t = self.mm.newTemplate(name)
        self.mm.addTemplate(self.model, t)
        self.redraw()

    # Closing & Help
    ######################################################################

    def accept(self):
        self.reject()

    def reject(self):
        self.mm.save(self.model)
        self.mw.reset()
        saveGeom(self, "CardLayout")
        return QDialog.reject(self)

    def onHelp(self):
        openHelp("CardLayout")
