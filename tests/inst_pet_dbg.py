# -*- coding: utf-8 -*-
"""临时插桩：在拖拽用例中打印状态"""
import io

P = r"D:\Projects\IELTS-Word-Reminder\tests\functional_test.py"
s = io.open(P, encoding="utf-8").read()
old = (
    "    pet.mousePressEvent(press)\n"
    "    pet.mouseReleaseEvent(rel)\n"
    '    report("\u684c\u5ba0: \u62d6\u62fd\u540e\u8fdb\u5165\u81ea\u7531\u6a21\u5f0f"'
)
new = (
    "    pet.mousePressEvent(press)\n"
    "    print('DBG dragging after press:', pet._dragging)\n"
    "    pet.mouseReleaseEvent(rel)\n"
    "    print('DBG after rel mode:', pet._mode, 'dragging:', pet._dragging, 'base:', pet._base_pos, 'pos:', (pet.pos().x(), pet.pos().y()))\n"
    '    report("\u684c\u5ba0: \u62d6\u62fd\u540e\u8fdb\u5165\u81ea\u7531\u6a21\u5f0f"'
)
assert s.count(old) == 1, "target not found"
s = s.replace(old, new)
io.open(P, "w", encoding="utf-8").write(s)
print("instrumented")
