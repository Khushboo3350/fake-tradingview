from datetime import datetime, timezone
from time import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph import QtCore, QtGui

from utils import Worker, logger


class CandlestickItem(pg.GraphicsObject):
    sigXRangeChanged = QtCore.pyqtSignal()
    sigResized = QtCore.pyqtSignal()
    onUpdate = QtCore.pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.step = None
        self.anchor = None
        self.data = None
        self.ds = 1
        self.path = None
        self.limit = 500
        self.plotting = False

        self.autoRangeEnabled = True
        self._boundingRect = None
        self._boundsCache = [None, None]

        # Data init
        self.anchor, data = self.db.getOHLC()
        self.setData(data)

    def refresh(self):
        if not self.plotting:
            self.plotting = True
            # self.updateOHLC(True)
            worker = Worker(self.updateOHLC, True)
            QtCore.QThreadPool.globalInstance().start(worker)

    def setIndex(self, index):
        self.plotting = True
        self.db.setIndex(index)
        self.anchor, data = self.db.getOHLC(fetchLive=True)
        self.plotting = False

        self.setData(data)

    def setInterval(self, interval):
        self.dateFormat = self.db.getDateFormat()

        self.plotting = True
        self.db.setInterval(interval)
        self.anchor, data = self.db.getOHLC(fetchLive=True)
        self.plotting = False

        self.setData(data)

    def setData(self, data):
        self.data = data

        self.invalidateBounds()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()

        self.path = None
        self.update()
        self.onUpdate.emit()

    def updateOHLC(self, refresh=False):
        vb = self.getViewBox()
        if vb is None:
            self.plotting = False
            return  # no ViewBox yet
        else:
            xRange = vb.viewRange()[0]
            if xRange[1] - xRange[0] == 1:
                self.plotting = False
                return

        start, stop = xRange
        self.anchor, data = self.db.getOHLC(start, stop, refresh)

        try:
            step = data[1][0] - data[0][0]
        except IndexError:
            ds = 1
        else:
            ds = int((stop - start) / (step * self.limit)) + 1
            # logger.debug([ds, len(data)])

        if ds == 1:
            # Small enough to display with no intervention.
            visible = data
        else:
            # Here convert data into a down-sampled array suitable for visualizing.
            # Cut off to fix bar jitter
            chunk = data[: (len(data) // ds) * ds]
            anchor = (data[0][0] - self.anchor) / step
            offset = int(anchor % ds)
            if offset:
                chunk = chunk[ds - offset : -offset]
            visible = np.zeros((len(chunk) // ds, 5))

            # Reshape timestamp
            visible[:, 0] = chunk[: (len(chunk) // ds) * ds : ds, 0]

            # Reshape open
            _open = chunk[: (len(chunk) // ds) * ds, 1].reshape(len(chunk) // ds, ds)
            if np.isnan(_open).any():
                visible[:, 1] = self.filterNan(_open, first=True)
            else:
                visible[:, 1] = chunk[: (len(chunk) // ds) * ds : ds, 1]

            # Reshape high
            high = chunk[: (len(chunk) // ds) * ds, 2].reshape(len(chunk) // ds, ds)
            if np.isnan(high).any():
                high = np.nan_to_num(high, nan=-np.inf)
            visible[:, 2] = high.max(axis=1)

            # Reshape low
            low = chunk[: (len(chunk) // ds) * ds, 3].reshape(len(chunk) // ds, ds)
            if np.isnan(low).any():
                low = np.nan_to_num(low, nan=np.inf)
            visible[:, 3] = low.min(axis=1)

            # Reshape close
            close = chunk[: (len(chunk) // ds) * ds, 4].reshape(len(chunk) // ds, ds)
            if np.isnan(close).any():
                visible[:, 4] = self.filterNan(close, first=False)
            else:
                visible[:, 4] = chunk[: (len(chunk) // ds) * ds : ds, 4]

        self.ds = ds
        self.setData(visible)  # update the plot
        self.resetTransform()
        self.plotting = False

    def paint(self, p, *args):
        redBars, greenBars = self.getPath()

        p.setPen(pg.mkPen("g"))
        p.setBrush(pg.mkBrush("g"))
        p.drawPath(greenBars)

        p.setPen(pg.mkPen("r"))
        p.setBrush(pg.mkBrush("r"))
        p.drawPath(redBars)

    def getPath(self):
        if self.path is None:
            if self.data is None or len(self.data) < 2:
                self.path = [QtGui.QPainterPath(), QtGui.QPainterPath()]
            else:
                redBars = QtGui.QPainterPath()
                greenBars = QtGui.QPainterPath()

                self.step = self.data[1][0] - self.data[0][0]
                w = self.step / 3.0
                for data in self.data:
                    if not np.isnan(data).any():
                        t, o, h, l, c = data
                        if o > c:
                            redBars.moveTo(QtCore.QPointF(t, l))
                            redBars.lineTo(QtCore.QPointF(t, h))
                            redBars.addRect(QtCore.QRectF(t - w, o, w * 2, c - o))
                        else:
                            greenBars.moveTo(QtCore.QPointF(t, l))
                            greenBars.lineTo(QtCore.QPointF(t, h))
                            greenBars.addRect(QtCore.QRectF(t - w, o, w * 2, c - o))

                self.path = [redBars, greenBars]

        return self.path

    def invalidateBounds(self):
        self._boundingRect = None
        self._boundsCache = [None, None]

    def boundingRect(self):
        if self._boundingRect is None:
            (xmn, xmx) = self.dataBounds(ax=0)
            (ymn, ymx) = self.dataBounds(ax=1)
            if xmn is None or ymn is None:
                return QtCore.QRectF()

            px = py = 0.0
            self._boundingRect = QtCore.QRectF(
                xmn - px, ymn - py, (2 * px) + xmx - xmn, (2 * py) + ymx - ymn
            )

        return self._boundingRect

    def dataBounds(self, ax, frac=1.0, orthoRange=None):
        cache = self._boundsCache[ax]
        if cache is not None and cache[0] == (frac, orthoRange):
            return cache[1]

        if self.data is None:
            return (None, None)

        x = self.data[:, 0]
        y = self.data[:, 1:]

        if ax == 0:
            d = x
            d2 = y
        elif ax == 1:
            d = y
            d2 = x

        if orthoRange is not None:
            mask = (d2 >= orthoRange[0]) * (d2 <= orthoRange[1])
            d = d[mask]

        if len(d) == 0:
            return (None, None)

        b = (np.nanmin(d), np.nanmax(d))

        if any(np.isinf(b)):
            mask = np.isfinite(d)
            d = d[mask]
            if len(d) == 0:
                return (None, None)
            b = (d.min(), d.max())

        self._boundsCache[ax] = [(frac, orthoRange), b]
        return b

    def viewTransformChanged(self):
        self.invalidateBounds()
        self.prepareGeometryChange()

    def viewRangeChanged(self):
        if not self.plotting:
            self.plotting = True
            worker = Worker(self.updateOHLC)
            QtCore.QThreadPool.globalInstance().start(worker)
            self.sigXRangeChanged.emit()
            self.sigResized.emit()

    def filterNan(self, inputArray, first):
        outputArray = []
        for array in inputArray:
            if np.isnan(array).all():
                outputArray.append(np.nan)
            else:
                if first:
                    outputArray.append(array[~np.isnan(array)][0])
                else:
                    outputArray.append(array[~np.isnan(array)][-1])

        return outputArray
