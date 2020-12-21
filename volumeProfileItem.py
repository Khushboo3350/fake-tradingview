import datetime

import numpy as np
import pandas as pd
import pyqtgraph as pg
from dateutil.tz import tzlocal
from pyqtgraph import QtCore, QtGui
from sklearn.preprocessing import minmax_scale


class VolumeProfileItem(pg.GraphicsObject):
    onUpdate = QtCore.pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.data = []
        self.picture = QtGui.QPicture()
        self.textItems = []

    def getDate(self):
        return self.db.getDate()

    def setAlpha(self, index, value):
        self.data[index][4] = value
        self.updateData()

    def updateData(self):
        self.picture = QtGui.QPicture()
        p = QtGui.QPainter(self.picture)

        for x, y, df, step, alpha in self.data:
            p.setPen(pg.mkPen(63, 63, 63, alpha))
            p.setBrush(pg.mkBrush(63, 63, 63, alpha))
            p.drawRect(QtCore.QRectF(x[0], y[1], x[1] - x[0], y[0] - y[1]))

            x_length = x[1] - x[0]
            x_pos = minmax_scale(df.to_numpy(), (0.1 * x_length, x_length / 2))
            for interval, width in zip(df.index, x_pos):
                p.setBrush(pg.mkBrush(0, 255, 0, alpha))
                p.drawRect(QtCore.QRectF(x[0], interval.left, width[0], step))

                p.setBrush(pg.mkBrush(255, 0, 0, alpha))
                p.drawRect(
                    QtCore.QRectF(x[0] + width[0], interval.left, width[1], step)
                )

        p.end()
        self.update()

    def addText(self, data):
        formatter = lambda x: str(round(x / 1e06, 2)) + "M"

        x, y, df, _, _ = data

        total = df.sum(axis=0)
        item = pg.TextItem(
            "Total: " + formatter(total[0]) + " X " + formatter(total[1])
        )
        item.setPos(x[0], y[0])
        item.setParentItem(self)

        items = [item]
        for interval, volume in zip(df.index, df.to_numpy()):
            item = pg.TextItem(
                formatter(volume[0]) + " X " + formatter(volume[1]), anchor=(0, 0.5),
            )
            item.setPos(x[0], interval.mid)
            item.setParentItem(self)
            items.append(item)

        self.textItems.append(items)

    def addData(self, start, end, num):
        x = [start.toUTC().toSecsSinceEpoch(), end.toUTC().toSecsSinceEpoch()]
        if (start < end) and (x not in [data[0] for data in self.data]):
            df, y, step = self.db.volumeOnPrice(
                start.toPyDateTime(), end.toPyDateTime(), num
            )
            data = [x, y, df, step, 127]

            self.data.append(data)
            self.addText(data)
            self.updateData()
            return True
        else:
            return False

    def removeData(self, index):
        for i in self.textItems[index]:
            self.scene().removeItem(i)
        self.textItems.pop(index)

        self.data.pop(index)
        self.updateData()

    def removeAll(self):
        for _ in range(len(self.data)):
            for i in self.textItems[0]:
                i.scene().removeItem(i)
            self.textItems.pop(0)
            self.data.pop(0)

        self.updateData()

    def paint(self, p, *args):
        self.picture.play(p)
        self.onUpdate.emit()

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

    def dataBounds(self, ax, frac=1.0, orthoRange=None):
        return (None, None)

