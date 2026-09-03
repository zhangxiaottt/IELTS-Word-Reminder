# -*- coding: utf-8 -*-
"""临时插桩：打印坐标与 moved"""
import io

P = r"D:\Projects\IELTS-Word-Reminder\tests\functional_test.py"
s = io.open(P, encoding="utf-8").read()
old = (
    "    pet.mousePressEvent(press)\n"
    "    print('DBG dragging after press:', pet._dragging)\n"
    "    pet.mouseReleaseEvent(rel)\n"
    "    print('DBG after rel mode:', pet._mode, 'dragging:', pet._dragging, 'base:', pet._base_pos, 'pos:', (pet.pos().x(), pet.pos().y()))\n"
)
new = (
    "    print('DBG gp0:', gp0, 'gp1:', gp1, 'pressg:', press.globalPosition().toPoint(), 'relg:', rel.globalPosition().toPoint())\n"
    "    pet.mousePressEvent(press)\n"
    "    print('DBG dragging after press:', pet._dragging, 'press_global:', pet._drag_press_global)\n"
    "    pet.mouseReleaseEvent(rel)\n"
    "    print('DBG after rel mode:', pet._mode, 'dragging:', pet._dragging, 'base:', pet._base_pos, 'pos:', (pet.pos().x(), pet.pos().y()))\n"
)
assert s.count(old) == 1, "target not found"
s = s.replace(old, new)
io.open(P, "w", encoding="utf-8").write(s)
print("instrumented2")
