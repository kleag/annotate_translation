import ast
import ipdb
import sys
import os

import Ui_annotation
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget
from PyQt5.QtGui import QTextCharFormat, QTextCursor
import pandas as pd
import json
from PyQt5.QtCore import Qt, QThread


class WorkThread(QThread):
    def __init__(self):
        super(WorkThread,self).__init__()
    def run(self):
        global output, output_filename
        if len(output) > 0:
            output.to_csv(os.path.join('./output', output_filename), sep='\t', encoding='utf-8')


def normalize_entity(entity):
    if len(entity) == 0:
        return entity
    while len(entity) > 0 and entity[-1] in ',.;:!?':
        entity = entity[:-1]
    return entity


def selectedText_is_consecutive_words(select_text, origin_text, char_start_idx, char_end_idx):
    #breakpoint()
    # Yes | Yes, this hospital does have 3.0T MRI equipment. | 0 | 3
    words = [normalize_entity(e) for e in origin_text.lower().split(' ')]
    select_text_2 = select_text.strip()
    # char idx changed, ignore space
    if select_text_2 != select_text:
        left_len = select_text.find(select_text_2)
        right_len = len(select_text) - left_len - len(select_text_2)
        char_start_idx = char_start_idx + left_len
        char_end_idx = char_end_idx - right_len
    select_words = [normalize_entity(e) for e in select_text_2.lower().split(' ')]
    # Get all possible consecutive words whose length is equal to the length of select_words
    for i in range(len(words) - len(select_words) + 1):
        if words[i:i+len(select_words)] == select_words:
            return True, i, i+len(select_words), char_start_idx, char_end_idx
    return False, 0, 0, 0, 0


def change_word_to_char_highlight(texts, word_highlight):
    char_highlight = []
    for i in range(len(texts)):
        text = texts[i]
        text_split = text.strip().split(' ')
        char_highlight.append([])
        for j in range(len(word_highlight[i])):
            entity_word_span = word_highlight[i][j]
            entity = text_split[entity_word_span[0]:entity_word_span[1]]
            entity = ' '.join(entity)
            char_start_idx = text.find(entity)
            char_end_idx = char_start_idx + len(entity)
            char_highlight[i].append([char_start_idx, char_end_idx])
    return char_highlight


class MainDialog(QWidget):
    """
    The main class, holding all application data. It is also the main window of the
    application.

    ...

    Attributes
    ----------
    source_word_spans : [ [ [int, int], … ], … ]
        a list of lists of pairs of token numbers. For each utterance, the list of its
        token spans that define entities. Initialized from the csv file.
    source_word_highlight :  [ [ [int, int], … ], … ]
        a list of lists of pairs of token numbers. For each utterance, the list of its
        token spans that should be highlighted. Initialized from the json input.
        ex.: [[[9, 12]], [[2, 5]], [[6, 7], [1, 4]], …];
    source_highlight : [ [ [int, int], … ], … ]
        a list of lists of pairs of character positions. For each utterance, the list of
        its character spans that should be highlighted. It is computed from
        source_word_highlight
        ex.: [[[46, 64]], [[11, 28]], [[29, 35], [2, 19]], …]
    target_word_spans : [ [ [int, int], … ], … ]
        a list of lists of pairs of token numbers. For each translated utterance, the
        list of its token spans that define entities. Initialized from the csv file.
    target_word_highlight : [ [ [int, int], … ], … ]
        a list of lists of pairs of token numbers. For each translated utterance, the
        list of its token spans that should be highlighted. To be filled from
        target_word_spans after loading the csv file
        ex.: [[[9, 12]], [[2, 5]], [[6, 7], [1, 4]], …];
    target_highlight : [ [ [int, int], … ], … ]
        a list of lists of pairs of character positions. For each translated utterance,
        the list of its character spans that should be highlighted. It is computed from
        target_word_highlight
        ex.: [[[46, 64]], [[11, 28]], [[29, 35], [2, 19]], …]

    Methods
    -------
    """

    def __init__(self, parent=None):
        super(MainDialog, self).__init__(parent)
        self.ui = Ui_annotation.Ui_Form()
        self.ui.setupUi(self)

        self.ui.read.clicked.connect(self.read_file)
        self.ui.previous.clicked.connect(self.previous_item)
        self.ui.reset.clicked.connect(self.reset_item)
        self.ui.next.clicked.connect(self.next_item)
        self.ui.add_source.clicked.connect(self.add_source_entity)
        self.ui.add_target.clicked.connect(self.add_target_entity)
        self.ui.clear.clicked.connect(self.clear_entity)
        self.ui.id.valueChanged.connect(self.move_to_item)

        self.cwd = os.getcwd()  # Get current file path

        self.box1 = QMessageBox(QMessageBox.Warning, 'warn', "It's already the first one")
        self.box2 = QMessageBox(QMessageBox.Warning, 'warn', 'It is already the last one')
        self.box3 = QMessageBox(QMessageBox.Warning, 'warn', 'Please add a Source entity first')
        self.box4 = QMessageBox(QMessageBox.Warning, 'warn', 'Please add an Target entity first')
        self.box5 = QMessageBox(QMessageBox.Warning, 'warn', 'Please make true the selected text is consecutive words!')
        self.box6 = QMessageBox(QMessageBox.Warning, 'warn', 'Invalid utterance number.')

    def read_file(self):
        # init
        self.source_texts = []
        self.target_texts = []
        self.source_highlight = []
        self.source_word_highlight = [] # 3 dimension，用于高亮需要本地化的实体
        self.source_entities = [] # 嵌套列表 - Nested List
        self.target_highlight = []
        self.target_word_highlight = [] # 3 dimension，突出显示已经定位的实体
        self.target_entities = [] # 嵌套列表 - Nested List
        self.source_spans = []
        self.source_word_spans = []
        self.target_spans = []
        self.target_word_spans = []
        self.dialogue_id = []
        self.turn_id = []
        self.utterance_type = []

        self.cur_index = 0

        global output # global variable
        output = pd.DataFrame(columns=['source', 'target', 'source_entity', 'target_entity', \
                            'source_span', 'target_span', 'dialogue_id', 'turn_id', 'utterance_type', \
                            'source_word_span', 'target_word_span'])
        self.write_output = WorkThread()

        # choose file
        fileName_choose, filetype = QFileDialog.getOpenFileName(self, "choose file",
                                                                self.cwd,
                                                                "All Files (*)")
        print(fileName_choose)
        if fileName_choose == '':
            return
        if not os.path.exists('./output') and not os.path.isdir('./output'):
            os.mkdir('./output/')
        global output_filename
        output_filename = os.path.split(fileName_choose)[-1].split('.')[0] + '_output.csv'

        # read json file
        # try different encoding
        try:
            with open(fileName_choose, 'r', encoding='utf-8') as f:
                content = json.load(f)
        except Exception as err:
            try:
                print("Error begin:"+fileName_choose+"  "+str(err))
                with open(fileName_choose, 'r', encoding='gbk') as f:
                    content = json.load(f)
            except Exception as err2:
                try:
                    print("Error two:"+fileName_choose+"  "+str(err2))
                    with open(fileName_choose, 'r', encoding='gb2312') as f:
                        content = json.load(f)
                except Exception as err3:
                    print("Error do not know:"+fileName_choose+"  "+str(err3))
                    QMessageBox.critical(self, "Error", "Unknown file encoding!", QMessageBox.Yes)
                    raise err3

        for dialogue in content:
            dialogue_detail = dialogue['dialogue']
            for turn in dialogue_detail:
                self.source_texts.append(turn['user_utterance'][0])
                self.dialogue_id.append(dialogue['dialogue_id'])
                self.turn_id.append(turn['turn_id'])
                self.utterance_type.append('user')
                # Compute source highlight for user utterance from json data
                # Target highlight will be computed when loading csv
                if len(self.source_word_highlight) < len(self.source_texts):
                    self.source_word_highlight.append([])
                for k, v in turn['user_utterance'][1].items():
                    for kk, vv in v.items():
                        for vvv in vv:
                            self.source_word_highlight[-1].append(vvv)
                self.source_texts.append(turn['system_utterance'][0])
                self.dialogue_id.append(dialogue['dialogue_id'])
                self.turn_id.append(turn['turn_id'])
                self.utterance_type.append('system')
                # Compute source highlight for system utterance from json data
                # Target highlight will be computed when loading csv
                if len(self.source_word_highlight) < len(self.source_texts):
                    self.source_word_highlight.append([])
                for k, v in turn['system_utterance'][1].items():
                    for kk, vv in v.items():
                        for vvv in vv:
                            self.source_word_highlight[-1].append(vvv)
        # change word hightlight to char highlight
        self.source_highlight = change_word_to_char_highlight(self.source_texts, self.source_word_highlight)
        # restore
        if os.path.exists(os.path.join('./output', output_filename)):
            QMessageBox.warning(self, 'warn', 'Some annotations have been recovered from %s in the output folder' % output_filename, QMessageBox.Yes)
            annotation = pd.read_csv(os.path.join('./output', output_filename), sep='\t', encoding='utf-8')
            self.load_csv_data(annotation)

            # 预添加空列表 - Pre-added empty lists
            self.source_entities.append([])
            self.target_entities.append([])
            self.source_spans.append([])
            self.source_word_spans.append([])
            self.target_spans.append([])
            self.target_word_spans.append([])
            # 显示标注文件的最后一条 - Display the last entry of the markup file
            tmp_index = self.cur_index - 1
            self.cur_index = self.cur_index-1

            tmp_source_text = self.source_texts[tmp_index]
            tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[tmp_index])
            self.ui.source.setText(tmp_source_text)

            #self.ui.target.setText(self.target_texts[tmp_index])
            tmp_target_text = self.target_texts[tmp_index]
            if len(self.target_highlight) > tmp_index:
                tmp_target_text = self.change_span_style(tmp_target_text, self.target_highlight[tmp_index])
            self.ui.target.setText(tmp_target_text)

            self.ui.source_entity.clear()
            for i in range(len(self.source_entities[tmp_index])):
                display_source_text = self.source_entities[tmp_index][i] + '  -  ' + str(self.source_word_spans[tmp_index][i])
                self.ui.source_entity.addItem(display_source_text)
            self.ui.target_entity.clear()
            for i in range(len(self.target_entities[tmp_index])):
                display_target_text = self.target_entities[tmp_index][i] + '  -  ' + str(self.target_word_spans[tmp_index][i])
                self.ui.target_entity.addItem(display_target_text)
            self.ui.id.setRange(1, len(self.source_texts))
            self.ui.id.setSuffix(f"/ {str(len(self.source_texts))}")
            self.ui.id.setValue(tmp_index+1)
        else:
            # 预添加空列表 - Pre-added empty lists
            self.source_entities.append([])
            self.target_entities.append([])
            self.source_spans.append([])
            self.source_word_spans.append([])
            self.target_spans.append([])
            self.target_word_spans.append([])            # display data
            tmp_source_text = self.source_texts[self.cur_index]
            tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
            self.ui.source.setText(tmp_source_text)
            self.ui.target.clear()
            self.ui.source_entity.clear()
            self.ui.target_entity.clear()
            self.ui.id.setRange(1, len(self.source_texts))
            self.ui.id.setSuffix(f"/ {str(len(self.source_texts))}")
            self.ui.id.setValue(self.cur_index+1)

    def load_csv_data(self, annotation):
        for i in range(len(annotation)):
            item = annotation.iloc[i]
            tmp_target_text = item['target'] if str(item['target']) != 'nan' else ''
            self.target_texts.append(tmp_target_text)
            self.source_entities.append(ast.literal_eval(item['source_entity']))
            self.target_entities.append(ast.literal_eval(item['target_entity']))
            self.source_spans.append(ast.literal_eval(item['source_span']))
            self.target_spans.append(ast.literal_eval(item['target_span']))
            self.source_word_spans.append([])
            self.target_word_spans.append([])
            self.get_word_spans(i, self.source_spans, self.source_word_spans,
                                self.source_entities, self.source_texts)
            self.get_word_spans(i, self.target_spans, self.target_word_spans,
                                self.target_entities, self.target_texts)
            self.target_word_highlight = self.target_word_spans

            output.loc[self.cur_index] = [self.source_texts[self.cur_index], self.target_texts[self.cur_index], \
                        self.source_entities[self.cur_index], self.target_entities[self.cur_index], \
                        self.source_spans[self.cur_index], self.target_spans[self.cur_index], \
                        self.dialogue_id[self.cur_index], self.turn_id[self.cur_index], self.utterance_type[self.cur_index], \
                        self.source_word_spans[self.cur_index], self.target_word_spans[self.cur_index]
                        ]
            self.cur_index += 1
        # change word hightlight to char highlight
        self.target_highlight = change_word_to_char_highlight(
            self.target_texts, self.target_word_highlight)

    def get_word_spans(self, i, spans, word_spans, entities, texts):
        for span_i in range(len(spans[i])):
            span = spans[i][span_i]
            result, word_start_idx, word_end_idx, char_start_idx, char_end_idx = selectedText_is_consecutive_words(
                        entities[i][span_i], texts[i], span[0], span[1])
            if result:
                word_spans[i].append([word_start_idx, word_end_idx])
            else:
                print(f"selectedText is NOT consecutive_words: "
                      f"{entities[i][span_i]} | {texts[i]} | {span[0]} | {span[1]}",
                      file=sys.stderr)
                word_spans[i].append([0, 0])

    def change_span_style(self, text, spans): # spans为二维数组
        # print(spans)
        # 将spans转成元组后再去重
        spans = [tuple(span) for span in spans]
        spans = list(set(spans))
        spans = sorted(spans, key=lambda x: x[0])
        new_spans = [] # 保存处理完“两个span各种相对位置”情况后的结果
        i = 0
        while i < len(spans):
            j = i+1
            # 首 重合的情况
            if j < len(spans) and spans[j][0]==spans[i][0]:
                while j < len(spans) and spans[j][0]==spans[i][0]:
                    if spans[j][1] > spans[i][1]:
                        i = j
                        j = i+1
                    elif spans[j][1] < spans[i][1]:
                        j+=1
                new_spans.append(spans[i])
                i = j
            # 首 不重合但第二个span的首位于第一个span的尾之前 的情况
            elif j < len(spans) and spans[j][0] < spans[i][1]:
                j = i+1
                if i < len(spans):
                    while j < len(spans) and spans[j][0] < spans[i][1] and spans[j][1] <= spans[i][1]:
                            j+=1
                    new_spans.append(spans[i])
                    i = j
            else:
                new_spans.append(spans[i])
                i = j
        # print(new_spans)

        increased_index = 0
        for span in new_spans:
            start = span[0] + increased_index
            end = span[1] + increased_index
            text = text[:start] + '<u><b>' + text[start:end] + '</u></i>' + text[end:]
            increased_index += len('<u><b></b></u>')
        return text

    def add_source_entity(self):
        if len(self.target_entities[self.cur_index]) == len(self.source_entities[self.cur_index]):
            tc = self.ui.source.textCursor()
            if tc.selectedText() != '':
                result, word_start_idx, word_end_idx, char_start_idx, char_end_idx = selectedText_is_consecutive_words(tc.selectedText(),
                                                    self.source_texts[self.cur_index], tc.selectionStart(), tc.selectionEnd())
                if result:
                    # change color
                    color_format = QTextCharFormat(tc.charFormat())
                    color_format.setForeground(Qt.red)
                    tc.mergeCharFormat(color_format)
                    self.source_entities[self.cur_index].append(tc.selectedText())
                    self.source_spans[self.cur_index].append([char_start_idx, char_end_idx])
                    self.source_word_spans[self.cur_index].append([word_start_idx, word_end_idx])
                    self.source_word_highlight[self.cur_index].append([word_start_idx, word_end_idx])
                    self.source_highlight = change_word_to_char_highlight(
                        self.source_texts, self.source_word_highlight)
                    self.ui.source_entity.clear()
                    for i in range(len(self.source_entities[self.cur_index])):
                        display_text = self.source_entities[self.cur_index][i] + '  -  ' + str(self.source_word_spans[self.cur_index][i]) + '\n'
                        self.ui.source_entity.addItem(display_text)
                else:
                    self.box5.show()
        else:
            self.box4.show()

    def add_target_entity(self):
        if len(self.target_entities[self.cur_index]) == len(self.source_entities[self.cur_index])-1:
            tc = self.ui.target.textCursor()
            if tc.selectedText() != '':
                result, word_start_idx, word_end_idx, char_start_idx, char_end_idx = selectedText_is_consecutive_words(tc.selectedText(),
                                                    self.ui.target.toPlainText(), tc.selectionStart(), tc.selectionEnd())
                if result:
                    color_format = QTextCharFormat(tc.charFormat())
                    color_format.setForeground(Qt.red)
                    tc.mergeCharFormat(color_format)
                    self.target_entities[self.cur_index].append(tc.selectedText())
                    self.target_spans[self.cur_index].append([char_start_idx, char_end_idx])
                    self.target_word_spans[self.cur_index].append([word_start_idx, word_end_idx])
                    self.target_word_highlight = self.target_word_spans
                    display_text = ""
                    for i in range(len(self.target_entities[self.cur_index])):
                        display_text = self.target_entities[self.cur_index][i] + '  -  ' + str(self.target_word_spans[self.cur_index][i])
                        self.ui.target_entity.addItem(display_text)
                else:
                    self.box5.show()
        else:
            self.box3.show()

    def clear_entity(self):
        if self.cur_index < len(self.source_entities):
            self.source_entities[self.cur_index] = []
            self.target_entities[self.cur_index] = []
            self.source_spans[self.cur_index] = []
            self.source_word_spans[self.cur_index] = []
            self.target_spans[self.cur_index] = []
            self.target_word_spans[self.cur_index] = []
            self.ui.source.setTextColor(Qt.black)
            self.ui.target.setTextColor(Qt.black)
            tmp_source_text = self.source_texts[self.cur_index]
            tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
            self.ui.source.setTextCursor(QTextCursor())
            self.ui.source.setText(tmp_source_text)
            self.ui.target.setText(self.ui.target.toPlainText())

            self.ui.source_entity.clear()
            self.ui.target_entity.clear()

    def previous_item(self):
        if self.cur_index == 0:
            self.box1.show()
        else:
            # save the current item
            self.save_current_item()
            # display old data
            self.cur_index -= 1
            self.ui.id.setText(str(self.cur_index+1)+' / '+str(len(self.source_texts)))
            old_data = output.loc[self.cur_index]
            self.ui.source.setTextColor(Qt.black)
            self.ui.target.setTextColor(Qt.black)
            tmp_source_text = old_data['source']
            tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
            # print(tmp_source_text)
            self.ui.source.setTextCursor(QTextCursor())
            self.ui.source.setText(tmp_source_text)
            tmp_target_text = old_data['target']
            if len(self.target_highlight) > self.cur_index:
                self.target_highlight = change_word_to_char_highlight(self.target_texts, self.target_word_highlight)
                tmp_target_text = self.change_span_style(tmp_target_text, self.target_highlight[self.cur_index])
            self.ui.target.setText(tmp_target_text)
            display_source_text = ""
            for i in range(len(old_data['source_entity'])):
                display_source_text += old_data['source_entity'][i] + '  -  ' + str(old_data['source_word_span'][i]) + '\n'
            self.ui.source_entity.setText(display_source_text)
            display_target_text = ""
            for i in range(len(old_data['target_entity'])):
                display_target_text += old_data['target_entity'][i] + '  -  ' + str(old_data['target_word_span'][i]) + '\n'
            self.ui.target_entity.setText(display_target_text)

    def reset_item(self):
        self.ui.source.setTextColor(Qt.black)
        self.ui.target.setTextColor(Qt.black)
        tmp_source_text = self.source_texts[self.cur_index]
        tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
        self.ui.source.setTextCursor(QTextCursor())
        self.ui.source.setText(tmp_source_text)
        self.ui.target.clear()
        self.ui.source_entity.clear()
        self.ui.target_entity.clear()
        self.source_entities[self.cur_index] = []
        self.target_entities[self.cur_index] = []
        self.source_spans[self.cur_index] = []
        self.source_word_spans[self.cur_index] = []
        self.target_spans[self.cur_index] = []
        self.target_word_spans[self.cur_index] = []

    def next_item(self):
        if not self.cur_index < len(self.source_texts):
            self.box2.show()
        else:
            self.save_current_item()

            # display new data
            if not self.cur_index+1 < len(self.source_texts):
                self.box2.show()
            else:
                self.cur_index += 1
                self.ui.id.setText(str(self.cur_index+1)+' / '+str(len(self.source_texts)))
                if self.cur_index < len(output):
                    # display old data
                    old_data = output.loc[self.cur_index]
                    self.ui.source.setTextColor(Qt.black)
                    self.ui.target.setTextColor(Qt.black)
                    tmp_source_text = old_data['source']
                    tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
                    self.ui.source.setTextCursor(QTextCursor())
                    self.ui.source.setText(tmp_source_text)
                    #self.ui.target.setText(old_data['target'])
                    tmp_target_text = old_data['target']
                    if len(self.target_highlight) > self.cur_index:
                        self.target_highlight = change_word_to_char_highlight(self.target_texts, self.target_word_highlight)
                        tmp_target_text = self.change_span_style(tmp_target_text, self.target_highlight[self.cur_index])
                    self.ui.target.setText(tmp_target_text)
                    display_source_text = ""
                    for i in range(len(old_data['source_entity'])):
                        display_source_text += old_data['source_entity'][i] + '  -  ' + str(old_data['source_word_span'][i]) + '\n'
                    self.ui.source_entity.setText(display_source_text)
                    display_target_text = ""
                    for i in range(len(old_data['target_entity'])):
                        display_target_text += old_data['target_entity'][i] + '  -  ' + str(old_data['target_word_span'][i]) + '\n'
                    self.ui.target_entity.setText(display_target_text)
                else:
                    self.ui.source.setTextColor(Qt.black)
                    tmp_source_text = self.source_texts[self.cur_index]
                    tmp_source_text = self.change_span_style(tmp_source_text, self.source_highlight[self.cur_index])
                    self.ui.source.setTextCursor(QTextCursor())
                    self.ui.source.setText(tmp_source_text)
                    self.ui.target.setTextColor(Qt.black)
                    self.ui.target.clear()
                    self.ui.source_entity.clear()
                    self.ui.target_entity.clear()
                    self.source_entities.append([])
                    self.target_entities.append([])
                    self.source_spans.append([])
                    self.source_word_spans.append([])
                    self.target_spans.append([])
                    self.target_word_spans.append([])


if __name__ == '__main__':
    myapp = QApplication(sys.argv)
    myDlg = MainDialog()
    myDlg.show()
    sys.exit(myapp.exec_())
