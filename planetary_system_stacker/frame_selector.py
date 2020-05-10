# -*- coding: utf-8; -*-
"""
Copyright (c) 2019 Rolf Hempel, rolf6419@gmx.de

This file is part of the PlanetarySystemStacker tool (PSS).
https://github.com/Rolf-Hempel/PlanetarySystemStacker

PSS is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PSS.  If not, see <http://www.gnu.org/licenses/>.

Part of this module (in class "AlignmentPointEditor" was copied from
https://stackoverflow.com/questions/35508711/how-to-enable-pan-and-zoom-in-a-qgraphicsview

"""
# The following PyQt5 imports must precede any matplotlib imports. This is a workaround
# for a Matplotlib 2.2.2 bug.

from glob import glob
from sys import argv, exit
from time import sleep

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from configuration import Configuration
from exceptions import Error
from frame_selector_gui import Ui_frame_selector
from frame_viewer import FrameViewer
from frames import Frames
from miscellaneous import Miscellaneous


class VideoFrameSelector(FrameViewer):
    """
    This widget implements a frame viewer for frames in a video file. Panning and zooming is
    implemented by using the mouse and scroll wheel.

    """

    resized = QtCore.pyqtSignal()

    def __init__(self, frames, index_included, frame_index=0):
        super(VideoFrameSelector, self).__init__()
        self.frames = frames
        self.index_included = index_included
        self.frame_index = frame_index

        self.setPhoto(self.frame_index)

    def setPhoto(self, index):
        """
        Convert a grayscale image to a pixmap and assign it to the photo object. If the image is
        marked as excluded from the stacking workflow, place a crossed-out red circle in the
        upper left image corner.

        :param index: Index into the frame list. Frames are assumed to be grayscale image in format
                      float32.
        :return: -
        """

        # Indicate that an image is being loaded.
        self.image_loading_busy = True

        image = self.frames.frames_mono(index)

        super(VideoFrameSelector, self).setPhoto(image,
                                                 overlay_exclude_mark=not self.index_included[
                                                     index])


class FrameSelectorWidget(QtWidgets.QFrame, Ui_frame_selector):
    """
    This widget implements a frame viewer together with control elements to visualize frame
    qualities, and to manipulate the stack limits.
    """

    def __init__(self, parent_gui, configuration, frames, stacked_image_log_file, signal_finished):
        """
        Initialization of the widget.

        :param parent_gui: Parent GUI object
        :param configuration: Configuration object with parameters
        :param frames: Frames object with all video frames
        :param stacked_image_log_file: Log file to be stored with results, or None.
        :param signal_finished: Qt signal with signature (str) to trigger the next activity when
                                the viewer exits.
        """

        super(FrameSelectorWidget, self).__init__(parent_gui)
        self.setupUi(self)

        # Keep references to upper level objects.
        self.parent_gui = parent_gui
        self.configuration = configuration
        self.stacked_image_log_file = stacked_image_log_file
        self.signal_finished = signal_finished
        self.frames = frames
        self.index_included = frames.index_included.copy()

        # Initialize the frame list selection.
        self.items_selected = None
        self.indices_selected = None

        # Set colors for the frame list.
        self.background_included = QtGui.QColor(130, 255, 130)
        self.foreground_included = QtGui.QColor(0, 0, 0)
        self.background_excluded = QtGui.QColor(120, 120, 120)
        self.foreground_excluded = QtGui.QColor(255, 255, 255)

        self.listWidget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        # Initialize the inclusion / exclusion state of frames in the frame list.
        for i in range(frames.number_original):
            frame_number = i + 1
            if self.index_included[i]:
                item = QtWidgets.QListWidgetItem("Frame %i included" % frame_number)
                item.setBackground(self.background_included)
                item.setForeground(self.foreground_included)
            else:
                item = QtWidgets.QListWidgetItem("Frame %i excluded" % frame_number)
                item.setBackground(self.background_excluded)
                item.setForeground(self.foreground_excluded)
            self.listWidget.addItem(item)

        self.listWidget.installEventFilter(self)
        self.listWidget.itemClicked.connect(self.select_items)
        self.addButton.clicked.connect(self.use_triggered)
        self.removeButton.clicked.connect(self.not_use_triggered)

        # Be careful: Indices are counted from 0, while widget contents are counted from 1 (to make
        # it easier for the user.
        self.frame_index = 0

        # Set up the frame viewer and put it in the upper left corner.
        self.frame_selector = VideoFrameSelector(self.frames, self.index_included, self.frame_index)
        self.frame_selector.setObjectName("framewiever")
        self.gridLayout.addWidget(self.frame_selector, 0, 0, 1, 3)

        # Initialize a variable for communication with the frame_player object later.
        self.run_player = False

        # Create the frame player thread and start it. The player displays frames in succession.
        # It is pushed on a different thread because otherwise the user could not stop it before it
        # finishes.
        self.player_thread = QtCore.QThread()
        self.frame_player = FramePlayer(self)
        self.frame_player.moveToThread(self.player_thread)
        self.frame_player.set_photo_signal.connect(self.frame_selector.setPhoto)
        self.player_thread.start()

        # Initialization of GUI elements
        self.slider_frames.setMinimum(1)
        self.slider_frames.setMaximum(self.frames.number)
        self.slider_frames.setValue(self.frame_index + 1)

        self.gridLayout.setColumnStretch(0, 7)
        self.gridLayout.setColumnStretch(1, 0)
        self.gridLayout.setColumnStretch(2, 0)
        self.gridLayout.setColumnStretch(3, 0)
        self.gridLayout.setColumnStretch(4, 1)
        self.gridLayout.setRowStretch(0, 0)
        self.gridLayout.setRowStretch(1, 0)

        # Connect signals with slots.
        self.buttonBox.accepted.connect(self.done)
        self.buttonBox.rejected.connect(self.reject)
        self.slider_frames.valueChanged.connect(self.slider_frames_changed)
        self.pushButton_play.clicked.connect(self.frame_player.play)
        self.pushButton_stop.clicked.connect(self.pushbutton_stop_clicked)

        if self.configuration.global_parameters_protocol_level > 0:
            Miscellaneous.protocol("+++ Start selecting frames +++", self.stacked_image_log_file)

    def select_items(self):
        """
        If a list item or a range of items is selected, store the items and corresponding indices.
        Set the frame slider to the first selected item and display it.

        :return: -
        """
        self.items_selected = self.listWidget.selectedItems()
        self.indices_selected = [self.listWidget.row(item) for item in self.items_selected]
        self.frame_index = self.indices_selected[0]

        # Set the slider to the current selection.
        self.slider_frames.blockSignals(True)
        self.slider_frames.setValue(self.frame_index + 1)
        self.slider_frames.blockSignals(False)

        # Update the image in the viewer.
        self.frame_selector.setPhoto(self.frame_index)  # print(self.indices_selected)

    def eventFilter(self, source, event):
        """
        This eventFilter is listening for events on the listWidget. List items can be marked as
        included / excluded by either using a context menu, by pressing the "+" or "-" buttons, or
        by pressing the keyboard keys "+" or "-".

        :param source: Source object to listen on.
        :param event: Event found
        :return: -
        """

        if source is self.listWidget:

            # Open a context menu with two choices. Depending on the user's choice, either
            # trigger the "use_triggered" or "not_use_triggered" method below.
            if event.type() == QtCore.QEvent.ContextMenu:
                menu = QtWidgets.QMenu()
                action1 = QtWidgets.QAction('Use for stacking', menu)
                action1.triggered.connect(self.use_triggered)
                menu.addAction((action1))
                action2 = QtWidgets.QAction("Don't use for stacking", menu)
                action2.triggered.connect(self.not_use_triggered)
                menu.addAction((action2))
                menu.exec_(event.globalPos())

            # Do the same as above if the user prefers to use the keyboard keys "+" or "-".
            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == Qt.Key_Plus:
                    self.use_triggered()
                elif event.key() == Qt.Key_Minus:
                    self.not_use_triggered()
                elif event.key() == Qt.Key_Escape:
                    self.items_selected = []
                    self.indices_selected = []
        return super(FrameSelectorWidget, self).eventFilter(source, event)

    def use_triggered(self):
        """
        The user has selected a list item or a range of items to be included in the stacking
        workflow. Change the appearance of the list entry, update the "index_included" values for
        the corresponding frames, and reload the image of the current index. The latter step is
        important to update the overlay mark in the upper left image corner.

        :return: -
        """

        if self.items_selected:
            for index, item in enumerate(self.items_selected):
                index_selected = self.indices_selected[index]
                frame_selected = index_selected + 1
                item.setText("Frame %i included" % frame_selected)
                item.setBackground(self.background_included)
                item.setForeground(QtGui.QColor(0, 0, 0))
                self.index_included[index_selected] = True
                self.frame_selector.setPhoto(self.frame_index)

    def not_use_triggered(self):
        """
        Same as above in case the user has de-selected a list item or a range of items.
        :return: -
        """

        if self.items_selected:
            for index, item in enumerate(self.items_selected):
                index_selected = self.indices_selected[index]
                frame_selected = index_selected + 1
                item.setText("Frame %i excluded" % frame_selected)
                item.setBackground(self.background_excluded)
                item.setForeground(QtGui.QColor(255, 255, 255))
                self.index_included[index_selected] = False
                self.frame_selector.setPhoto(self.frame_index)

    def slider_frames_changed(self):
        """
        The frames slider is changed by the user. Update the frame in the viewer and scroll the
        frame list to show the current frame index.

        :return: -
        """

        # Again, please note the difference between indexing and GUI displays.
        self.frame_index = self.slider_frames.value() - 1

        # Adjust the frame list and select the current frame.

        self.listWidget.setCurrentRow(self.frame_index, QtCore.QItemSelectionModel.SelectCurrent)
        self.select_items()

        # Update the image in the viewer.
        self.frame_selector.setPhoto(self.frame_index)
        self.listWidget.setFocus()

    def pushbutton_stop_clicked(self):
        """
        When the frame player is running, it periodically checks this variable. If it is set to
        False, the player stops.

        :return:
        """

        self.frame_player.run_player = False

    def done(self):
        """
        On exit from the frame viewer, update the selection status of all frames and send a
        completion signal.

        :return: -
        """

        # Check if the status of frames has changed.
        indices_included = []
        indices_excluded = []
        for index in range(self.frames.number_original):
            if self.index_included[index] and not self.frames.index_included[index]:
                indices_included.append(index)
                self.frames.index_included[index] = True
            elif not self.index_included[index] and self.frames.index_included[index]:
                indices_excluded.append(index)
                self.frames.index_included[index] = False

        # Write the changes in frame selection to the protocol.
        if self.configuration.global_parameters_protocol_level > 1:
            if indices_included:
                Miscellaneous.protocol(
                    "           The user has included the following frames into the stacking "
                    "workflow: " + str(
                        [item + 1 for item in indices_included]), self.stacked_image_log_file,
                    precede_with_timestamp=False)
            if indices_excluded:
                Miscellaneous.protocol(
                    "           The user has excluded the following frames from the stacking "
                    "workflow: " + str(
                        [item + 1 for item in indices_excluded]), self.stacked_image_log_file,
                    precede_with_timestamp=False)
            frames_remaining = sum(self.frames.index_included)
            if frames_remaining != self.frames.number:
                Miscellaneous.protocol("           " + str(
                    frames_remaining) + " frames will be used in the stacking workflow.",
                    self.stacked_image_log_file, precede_with_timestamp=False)

        # Send a completion message. The "execute_rank_frames" method is triggered on the workflow
        # thread. The signal payload is True if the status was changed for at least one frame.
        # In this case, the index translation table is updated before the frame ranking starts.
        if self.parent_gui is not None:
            self.signal_finished.emit(bool(indices_included) or bool(indices_excluded))

        # Close the Window.
        self.close()

    def reject(self):
        """
        If the "cancel" button is pressed, the coordinates are not stored.

        :return: -
        """

        # Send a completion message.
        if self.parent_gui is not None:
            self.signal_finished.emit(self.signal_payload)

        # Close the Window.
        self.close()


class FramePlayer(QtCore.QObject):
    """
    This class implements a video player using the FrameViewer and the control elements of the
    FrameViewerWidget. The player is started by the widget on a separate thread. This way the user
    can instruct the GUI to stop the running player.

    """
    set_photo_signal = QtCore.pyqtSignal(int)

    def __init__(self, frame_selector_widget):
        super(FramePlayer, self).__init__()

        # Store a reference of the frame selector widget and create a list of GUI elements. This
        # makes it easier to perform the same operation on all elements.
        self.frame_selector_widget = frame_selector_widget
        self.frame_selector_widget_elements = [self.frame_selector_widget.listWidget,
                                               self.frame_selector_widget.addButton,
                                               self.frame_selector_widget.removeButton]

        # Initialize a variable used to stop the player in the GUI thread.
        self.run_player = False

    def play(self):
        """
        Start the player.
        :return: -
        """

        # Block signals from GUI elements to avoid cross-talk, and disable them to prevent unwanted
        # user interaction.
        for element in self.frame_selector_widget_elements:
            element.blockSignals(True)
            element.setDisabled(True)

        # Set the player running.
        self.run_player = True

        while self.frame_selector_widget.frame_index < \
                self.frame_selector_widget.frames.number_original - 1 and self.run_player:
            if not self.frame_selector_widget.frame_selector.image_loading_busy:
                self.frame_selector_widget.frame_index += 1
                self.frame_selector_widget.slider_frames.setValue(
                    self.frame_selector_widget.frame_index + 1)
                self.set_photo_signal.emit(self.frame_selector_widget.frame_index)
            sleep(0.1)
            self.frame_selector_widget.update()

        self.run_player = False

        # Re-set the GUI elements to their normal state.
        for element in self.frame_selector_widget_elements:
            element.blockSignals(False)
            element.setDisabled(False)

        self.frame_selector_widget.listWidget.setFocus()


if __name__ == '__main__':
    # Images can either be extracted from a video file or a batch of single photographs. Select
    # the example for the test run.
    type = 'video'
    if type == 'image':
        names = glob(
            'Images/2012*.tif')  # names = glob.glob('Images/Moon_Tile-031*ap85_8b.tif')  # names
        # = glob.glob('Images/Example-3*.jpg')
    else:
        names = 'Videos/another_short_video.avi'
    print(names)

    # Get configuration parameters.
    configuration = Configuration()
    configuration.initialize_configuration()
    try:
        frames = Frames(configuration, names, type=type)
        print("Number of images: " + str(frames.number))
        print("Image shape: " + str(frames.shape))
    except Error as e:
        print("Error: " + e.message)
        exit()

    app = QtWidgets.QApplication(argv)
    window = FrameSelectorWidget(None, configuration, frames, None, None)
    window.setMinimumSize(800, 600)
    # window.showMaximized()
    window.show()
    app.exec_()

    exit()