#!/usr/bin/env python
# -*- coding: utf-8 -*-
import numpy as np
from xml.etree import ElementTree


class Rectangle:
    _instances = {}

    def __new__(cls, bounds):
        # 如果已经存在相同参数的实例，则返回该实例
        if bounds in cls._instances:
            return cls._instances[bounds]
        # 否则，创建新的实例并保存在类变量中
        instance = super(Rectangle, cls).__new__(cls)
        cls._instances[bounds] = instance
        return instance

    def __init__(self, bounds):
        # 如果实例是新创建的，则进行初始化
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.bounds = bounds
            self._bounds = [int(i) for i in bounds.replace("[", ",").replace("]", "").split(',') if i]

    @property
    def top_left(self):
        return self._bounds[0:2]

    @property
    def bottom_right(self):
        return self._bounds[2:]

    @property
    def center(self):
        return (self._bounds[0] + self._bounds[2]) / 2, (self._bounds[1] + self._bounds[3]) / 2

    @property
    def top_left_x(self):
        return self._bounds[0]

    @property
    def top_left_y(self):
        return self._bounds[1]

    @property
    def bottom_right_x(self):
        return self._bounds[2]

    @property
    def bottom_right_y(self):
        return self._bounds[3]

    @property
    def center_x(self):
        return (self._bounds[0] + self._bounds[2]) / 2

    @property
    def center_y(self):
        return (self._bounds[1] + self._bounds[3]) / 2

    @property
    def width(self):
        return self._bounds[2] - self._bounds[0]

    @property
    def height(self):
        return self._bounds[3] - self._bounds[1]

    @classmethod
    def clear_instances(cls):
        cls._instances.clear()

    def __repr__(self):
        return f"bounds:{self._bounds} at {id(self)}"


class AndroidTVFocus:
    def __init__(self):
        self.area_elements = []
        self.focus_element = None
        self.root = None
        self.focus_bounds = None

    def parse_layout_xml(self, page_source):
        # 解析 XML 文件，获取可点击且可获取焦点的元素及其父节点
        print('parse layout xm start')
        self.root = ElementTree.fromstring(page_source)
        focus_xpath = './/*[@focusable="true"][@focused="true"]'
        clickable_xpath = './/*[@focusable="true"][@clickable="true"]'

        # 获取当前焦点元素
        focus_element = self.root.find(focus_xpath)
        self.focus_bounds = focus_element.attrib.get('bounds')
        self.focus_element = Rectangle(self.focus_bounds)

        # 获取根元素
        root_element = self.root.find("./")

        # 获取全部可上焦点和点击的元素及父元素
        elements = self.root.findall(clickable_xpath)
        for element in elements:
            # 有为全屏且上焦的元素，必须去除，如OTT切全屏后返回
            if element.attrib.get('bounds') == root_element.attrib.get('bounds'):
                continue
            child = Rectangle(element.attrib.get('bounds'))
            if child in self.child_elements:
                continue

            parent = None
            for elem in self.root.iter():
                if element in elem:
                    parent = Rectangle(elem.attrib.get('bounds'))
                    break

            exist_dict = next((item for item in self.area_elements if item.get(parent)), None)

            # 如果存在，则将新数据添加到对应 key 的值后面
            if exist_dict:
                exist_dict[parent].append(child)
            else:
                # 否则，添加新的字典
                self.area_elements.append({parent: [child]})

        # 分割不规则区域
        for area in self.area_elements:
            for area_parent, area_children in area.items():

                ret = self.is_rule_area(area_children)
                if not ret:
                    self.area_elements.remove(area)
                    self.split_area(area_parent, area_children)
        # 父区域包含其它区域，缩小父区域范围，不可与上一个FOR循环（分割不规则区域）合并，会导致父对象增多
        for index, area in enumerate(self.area_elements):
            for area_parent, area_children in area.items():
                self.modify_area_range(area_children, index)
                self.sort_area_children(area_children, index)

    @property
    def parent_elements(self):
        return [key for item in self.area_elements for key in item.keys()]

    @property
    def child_elements(self):
        merged_list = [value for item in self.area_elements for value in item.values()]
        flat_list = [item for sublist in merged_list for item in sublist]
        return flat_list

    @staticmethod
    def is_in_area(current, target):
        cx1, cy1, cx2, cy2 = current.top_left_x, current.top_left_y, current.bottom_right_x, current.bottom_right_y
        tx1, ty1, tx2, ty2 = target.top_left_x, target.top_left_y, target.bottom_right_x, target.bottom_right_y
        if cx1 >= tx1 and cy1 >= ty1:
            if cx2 <= tx2 and cy2 <= ty2:
                return True
        return False

    def is_same_area(self, current, target):
        return self.get_parent_from_child(current) == self.get_parent_from_child(target)

    @staticmethod
    def calculate_size(elements):
        # 根据提供的数据计算矩阵的大小
        rows = len(set([y.center_y for y in elements]))
        cols = len(set([x.center_x for x in elements]))
        return rows, cols

    def is_rule_area(self, child_elements):
        # 判断是否规则的区域
        # 通过数量判断
        rows, cols = self.calculate_size(child_elements)
        if (rows - 1) * cols > len(child_elements):
            return False

        # 相同行通过y坐标判断在同一行，不同行通过与首比较x坐标判断在同一列
        for index, element in enumerate(child_elements):
            if index == 0:
                continue
            if element.center_y != child_elements[index-1].center_y and element.center_x != child_elements[0].center_x:
                return False
        # 不能通过大小判断，同一区域元素大小不一
        return True

    def split_area(self, area_parent, area_children):
        # 将不规则的区域分割成多个规则区域
        children = []
        for element in area_children:
            # 首次直接添加
            if len(children) == 0:
                children.append(element)
            else:
                center_x, center_y = element.center
                children_center_x = [item.center_x for item in children]
                children_center_y = [item.center_y for item in children]
                # y坐标坐标上能够找到相同的值说明在同一行，同一行时可不考虑元素宽度
                if center_y in children_center_y:
                    children.append(element)
                # x坐标坐标上能够找到相同的值说明可能在同一列，但同列时宽度不同可能会导致移动异常，新旧首行第一个中心点必须相同（精选-霸屏综艺）
                elif center_x == children_center_x[0]:
                    children.append(element)
                else:
                    # 获取区域子元素的最小最大坐标，将分割出的子元素生成新的父区域对象,区域内其它元素未处理原因是后续会统一进行处理。
                    # min_x = min(children, key=lambda d: d.top_left_x).top_left_x
                    # min_y = min(children, key=lambda d: d.top_left_y).top_left_y
                    # max_x = max(children, key=lambda d: d.bottom_right_x).bottom_right_x
                    # max_y = max(children, key=lambda d: d.bottom_right_y).bottom_right_y
                    # self.area_elements.append({Rectangle(f'[{min_x},{min_y}][{max_x},{max_y}]'): children})
                    self.modify_area_range(children)
                    children = [element]
        # 将最后剩余的同一区域添加到区域对象
        self.area_elements.append({Rectangle(area_parent.bounds): children})

    def modify_area_range(self, area_children, index=None):
        # 缩小区域范围
        min_x = min(area_children, key=lambda d: d.top_left_x).top_left_x
        min_y = min(area_children, key=lambda d: d.top_left_y).top_left_y
        max_x = max(area_children, key=lambda d: d.bottom_right_x).bottom_right_x
        max_y = max(area_children, key=lambda d: d.bottom_right_y).bottom_right_y
        if index is not None:
            self.area_elements[index] = {Rectangle(f'[{min_x},{min_y}][{max_x},{max_y}]'): area_children}
        else:
            self.area_elements.append({Rectangle(f'[{min_x},{min_y}][{max_x},{max_y}]'): area_children})

    def sort_area_children(self, area_children, index):
        # 规则区域的元素获取顺序变化需要排序，先根据y排序，再根据x排序
        sort_area_children = sorted(area_children, key=lambda child: (child.center[-1], child.center[0]))
        for key, _ in self.area_elements[index].items():
            self.area_elements[index][key] = sort_area_children

    def get_parent_from_child(self, child):
        for area in self.area_elements:
            for area_parent, area_children in area.items():
                if child in area_children:
                    return area_parent

    def get_children_from_child(self, child):
        for area in self.area_elements:
            for area_parent, area_children in area.items():
                if child in area_children:
                    return area_children

    def focus_in_area_move(self, target):
        # 计算从当前焦点位置移动到目标位置所需的步骤
        print('focus in area move start')
        area_children = self.get_children_from_child(self.focus_element)
        rows, cols = self.calculate_size(area_children)

        grid = [list(area_children[i:i + cols]) for i in range(0, rows * cols, cols)]
        element_positions = {char: (row, col) for row, row_elements in enumerate(grid) for col, char in
                             enumerate(row_elements)}
        move_order = []

        current = self.focus_element

        print(element_positions)
        while current.center != target.center:
            # 元素上焦点后有放大效果，导致坐标会发生变化，获取不到使用中心点重新获取
            element_current = element_positions.get(current)
            if not element_current:
                center = current.center
                current_row, current_col = {key.center: value for key, value in element_positions.items()}[center]
            else:
                current_row, current_col = element_positions[current]

            element_target = element_positions.get(target)
            if not element_target:
                center = target.center
                target_row, target_col = {key.center: value for key, value in element_positions.items()}[center]
            else:
                target_row, target_col = element_positions[target]

            row_diff = target_row - current_row
            col_diff = target_col - current_col
            if row_diff < 0:
                move_order.append('向上')
                current = grid[current_row - 1][current_col]
            # 设置页从1行最后一列向下移动时，下一行只有两个元素导致 grid[current_row + 1][current_col] 报错，增加列表报错判断
            elif row_diff > 0 and current_row + 1 < len(grid) and current_col < len(grid[current_row + 1]):
                move_order.append('向下')
                current = grid[current_row + 1][current_col]
            elif col_diff < 0:
                move_order.append('向左')
                current = grid[current_row][current_col - 1]
            elif col_diff > 0:
                move_order.append('向右')
                current = grid[current_row][current_col + 1]

        return move_order

    def is_adjacent(self, area1, area2):
        # 判断两个区域是否相邻，如相邻并area2在area1的哪个方向
        areas_list = [item.top_left + item.bottom_right for item in self.parent_elements]
        a1 = area1.top_left + area1.bottom_right
        a2 = area2.top_left + area2.bottom_right

        # 把区域列表转换为字典，方便引用
        areas = {f"area{i + 1}": areas_list[i] for i in range(len(areas_list))}
        # 判断是否在同一列（垂直方向上有重叠）
        if a1[0] < a2[2] and a1[2] > a2[0]:
            if a1[3] <= a2[1]:  # a1在a2上方
                # 检查在两区域间没有其他区域
                if not any(a1[3] <= areas[key][1] < a2[1] for key in areas if areas[key] != a1 and areas[key] != a2):
                    return True, "down"
            elif a2[3] <= a1[1]:  # a2在a1上方
                if not any(a2[3] <= areas[key][1] < a1[1] for key in areas if areas[key] != a1 and areas[key] != a2):
                    return True, "up"

        # 判断是否在同一行（水平方向上有重叠）
        if a1[1] < a2[3] and a1[3] > a2[1]:
            if a1[2] <= a2[0]:  # a1在a2左边
                # 检查在两区域间没有其他区域
                if not any(a1[2] <= areas[key][0] < a2[0] for key in areas if areas[key] != a1 and areas[key] != a2):
                    return True, "right"
            elif a2[2] <= a1[0]:  # a2在a1左边
                if not any(a2[2] <= areas[key][0] < a1[0] for key in areas if areas[key] != a1 and areas[key] != a2):
                    return True, "left"

        return False, "不相邻"

    def get_relative_position(self, area1, area2):
        x_distance = abs(area1.center_x - area2.center_x)
        y_distance = abs(area1.center_y - area2.center_y)

        # 判断相对位置
        relative_position = []

        # 判断上、下关系
        if area1.center_y < area2.center_y:
            relative_position.append("down")
        else:
            relative_position.append("up")

        # 判断左、右关系
        if area1.center_x < area2.center_x:
            relative_position.append("right")
        else:
            relative_position.append("left")

        # 根据距离排序，距离越远优先级更高
        if len(relative_position) > 1:
            if x_distance > y_distance:
                if relative_position[0] in ['up', 'down']:
                    relative_position.reverse()
            else:
                if relative_position[0] in ['left', 'right']:
                    relative_position.reverse()

        # 判断两区域是否相邻，相邻优先级更高
        ret, dire = self.is_adjacent(area1, area2)
        if ret and relative_position[-1] == dire:
            relative_position.reverse()

        return relative_position

    def focus_can_move_to_direction(self, focus, target, dire):
        # 当前区域对应方向上要有交叉的区域
        focus_parent = self.get_parent_from_child(self.focus_element)
        # 从focus改成focus_parent
        x1_min, y1_min = focus_parent.top_left
        x1_max, y1_max = focus_parent.bottom_right
        # distance1 = math.sqrt((focus.center_x - target.center_x) ** 2 + (focus.center_y - target.center_y) ** 2)
        for element in self.parent_elements:
            # 排序焦点父区域
            if element == focus_parent:
                continue

            x2_min, y2_min = element.top_left
            x2_max, y2_max = element.bottom_right
            # distance2 = math.sqrt((element.center_x - target.center_x) ** 2 + (element.center_y - target.center_y) ** 2)
            # # 区域距离更远不再进行下一步校验
            # if distance2 > distance1:
            #     print(f'{element} distance > {focus} distance')
            #     continue
            # 判断是否有交叉
            if dire in ['up', 'down']:
                if x1_max >= x2_min and x1_min <= x2_max:
                    if dire == 'up':
                        if y1_min > y2_min:
                            return True
                    elif dire == 'down':
                        if y1_min < y2_min:
                            return True
            else:
                if y1_max >= y2_min and y1_min <= y2_max:
                    if dire == 'left':
                        if x1_min > x2_min:
                            return True
                    elif dire == 'right':
                        if x1_min < x2_min:
                            return True
        return False

    def focus_move_out_area(self, target):
        print('focus move out area start')
        focus_parent = self.get_parent_from_child(self.focus_element)
        target_parent = self.get_parent_from_child(target)

        if not focus_parent or not target_parent:
            print(f'target:{target},focus:{self.focus_element},area:{self.area_elements}')
            # 自动启播等场景的UI变化导致目标bounds变化，返回一次等待，继续循环更正bounds
            return ['等待']

        relative_position = self.get_relative_position(focus_parent, target_parent)
        assert len(
            relative_position) > 0, f'relative position is null,focus:{self.focus_element},target:{target}'

        # 是否有交叉区域
        direction = None
        for direction in relative_position:
            if self.focus_can_move_to_direction(self.focus_element, target, direction):
                break
        assert direction is not None, f'relative position is direction null,focus:{self.focus_element},target:{target}'

        area_children = self.get_children_from_child(self.focus_element)
        rows, cols = self.calculate_size(area_children)
        grid = [list(area_children[i:i + cols]) for i in range(0, rows * cols, cols)]
        element_positions = {char: (row, col) for row, row_elements in enumerate(grid) for col, char in
                             enumerate(row_elements)}
        current_row, current_col = element_positions[self.focus_element]
        if direction == 'up':
            return ['向上'] * (current_row + 1)
        elif direction == 'down':
            return ['向下'] * (rows - current_row)
        elif direction == 'left':
            return ['向左'] * (current_col + 1)
        else:
            return ['向右'] * (cols - current_col)

    def move_to_target(self, page_source, target_bounds):
        Rectangle.clear_instances()
        self.area_elements = []
        self.parse_layout_xml(page_source)
        if self.focus_bounds == target_bounds:
            return []
        target = Rectangle(target_bounds)
        ret = self.is_same_area(self.focus_element, target)
        if ret:
            dire_list = self.focus_in_area_move(target)
        else:
            dire_list = self.focus_move_out_area(target)
        return dire_list



if __name__ == "__main__":
    # file_path = r"C:\Users\Dell\Desktop\source.xml"
    # with open(file_path, 'r', encoding='utf8') as f:
    #     xml = f.read()
    controller = AndroidTVFocus()
    from TestLibrary.AdbUtils import AdbUtils

    dir_dict = {'向上': 19, '向下': 20, '向左': 21, '向右': 22}
    adb = AdbUtils('192.168.1.100')
    _xpath = './/*[@content-desc="跳转图片"]'
    # _xpath = './/*[@text="子主题1"]/..'
    # _xpath = './/*[@text="关注"]'
    for i in range(10):
        xml = adb.run_adb_cmd('exec-out uiautomator dump /dev/tty')
        xml = xml.replace('UI hierchary dumped to: /dev/tty', '')
        root_1 = ElementTree.fromstring(xml)

        # 获取目标元素
        t_element = root_1.find(_xpath)
        b = t_element.attrib.get('bounds')
        # 解析布局文件
        x = controller.move_to_target(xml, b)
        print(x)
        if not x:
            break
        for i in x:
            adb.run_adb_shell_cmd(f'input keyevent {dir_dict[i]}')
            # time.sleep(0.6)

