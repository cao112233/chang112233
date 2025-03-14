from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class CutPiece:
    """需要切割的小料件"""

    length: float  # 长度
    count: int  # 需要的数量

    def __repr__(self):
        return f"{self.length}×{self.count}"

    def __hash__(self):
        return hash(self.length)

    def __eq__(self, other):
        if not isinstance(other, CutPiece):
            return False
        return self.length == other.length


@dataclass
class Stock:
    """原材料"""

    length: float  # 长度
    count: int  # 数量
    price: float  # 单价
    used: int = 0  # 已使用数量
    priority: bool = False  # 是否优先使用
    threshold: float = 0.0  # 利用率阈值

    def __repr__(self):
        return f"{self.length}×{self.count} (单价: {self.price})"


@dataclass
class CutPattern:
    """切割方案"""

    stock: Stock  # 使用的原材料
    pieces: List[Tuple[CutPiece, int]]  # 切割的小料件及数量
    waste: float  # 余料
    count: int = 1  # 使用该方案的次数

    def utilization(self) -> float:
        """计算该方案的利用率"""
        total_used = sum(piece.length * count for piece, count in self.pieces)
        return total_used / self.stock.length

    def __repr__(self):
        pieces_str = "  ".join(f"{p.length}×{c}" for p, c in self.pieces)
        return f"{self.stock.length}\t{pieces_str}\t{self.waste:.1f}\t{self.count}"


class CuttingStockSolver:

    def __init__(
        self,
        cut_pieces: List[Dict],
        stocks: List[Dict],
        cut_head: float = 20.0,
        kerf: float = 5.0,
    ):
        self.cut_pieces = [CutPiece(p["value"], p["count"]) for p in cut_pieces]
        self.stocks = [
            Stock(s["value"], s["count"], s["price"]) for s in stocks
        ]  # 加入单价
        self.cut_head = cut_head
        self.kerf = kerf
        self.patterns: List[CutPattern] = []
        self.remaining_counts = {piece: piece.count for piece in self.cut_pieces}

    def solve(self) -> List[CutPattern]:
        """求解下料问题"""
        # 按长度降序排序
        self.cut_pieces.sort(key=lambda x: x.length, reverse=True)

        while not self._all_pieces_cut():
            # 为每种原材料生成切割方案
            best_pattern = None
            best_utilization = 0.0

            for stock in self.stocks:
                if stock.used >= stock.count:
                    continue

                pattern = self._generate_pattern(stock)
                if pattern and pattern.utilization() > best_utilization:
                    best_pattern = pattern
                    best_utilization = pattern.utilization()

            if best_pattern:
                # 尝试合并相同的切割方案
                merged = False
                for existing_pattern in self.patterns:
                    if self._can_merge_patterns(existing_pattern, best_pattern):
                        existing_pattern.count += 1
                        best_pattern.stock.used += 1
                        merged = True
                        break

                if not merged:
                    self.patterns.append(best_pattern)
                    best_pattern.stock.used += 1

                self._update_cut_counts(best_pattern)
            else:
                break

        return self.patterns

    def _all_pieces_cut(self) -> bool:
        """检查是否所有料件都已切割完成"""
        return all(count <= 0 for count in self.remaining_counts.values())

    def _generate_pattern(self, stock: Stock) -> Optional[CutPattern]:
        """为指定原材料生成切割方案"""
        # 考虑料头损耗和去除料头的锯缝损耗
        remaining_length = stock.length - self.cut_head - self.kerf
        if remaining_length <= 0:
            return None  # 如果料头损耗和锯缝损耗已经超过了原材料长度，直接返回None

        pieces: List[Tuple[CutPiece, int]] = []

        # 贪心算法：尽可能多地放入最长的料件
        for piece in self.cut_pieces:
            if self.remaining_counts[piece] <= 0:
                continue

            # 计算当前剩余长度能放入多少个该料件
            available_length = remaining_length
            if len(pieces) > 0:  # 如果不是第一个料件，需要考虑前面已有的锯缝
                available_length += self.kerf  # 加回最后一个锯缝

            # 计算最大可切割数量
            max_count = min(
                self.remaining_counts[piece],
                int(available_length / (piece.length + self.kerf)),
            )

            if max_count > 0:
                # 计算实际需要的总长度，包括锯缝
                total_length_needed = (max_count * piece.length) + (
                    max_count * self.kerf  # 每次切割都会产生一次锯缝
                )

                # 确保不会超出剩余长度
                if total_length_needed <= remaining_length:
                    pieces.append((piece, max_count))
                    remaining_length -= total_length_needed

            # 如果剩余长度小于最小料件长度加锯缝，就停止
            min_piece_length = min(
                (p.length for p in self.cut_pieces if self.remaining_counts[p] > 0),
                default=0,
            )
            if min_piece_length > 0 and remaining_length < min_piece_length + self.kerf:
                break

        # 只有当有料件被放入且余量非负时才返回方案
        if pieces and remaining_length >= 0:
            # 计算总长度
            total_length = (
                sum(p.length * c for p, c in pieces)  # 料件长度总和
                + ((sum(c for _, c in pieces) - 1) * self.kerf)  # 锯缝损耗总和
                + self.cut_head  # 料头损耗
                + self.kerf  # 去除料头的锯缝损耗
            )
            # 计算余料
            waste = stock.length - total_length
            pattern = CutPattern(stock, pieces, waste)
            # 计算实际利用率，如果低于阈值则不使用该方案
            if stock.threshold > 0:
                if pattern.utilization() < stock.threshold:
                    return None
            return pattern

    def _can_merge_patterns(self, p1: CutPattern, p2: CutPattern) -> bool:
        """检查两个切割方案是否可以合并"""
        if p1.stock.length != p2.stock.length:
            return False

        if len(p1.pieces) != len(p2.pieces):
            return False

        for (piece1, count1), (piece2, count2) in zip(p1.pieces, p2.pieces):
            if piece1.length != piece2.length or count1 != count2:
                return False

        return True

    def print_completion(self):
        """打印下料任务的完成情况"""
        print("\n下料任务的完成情况:")
        for piece in self.cut_pieces:
            print(
                f"{piece.length}×{piece.count}：切割 {piece.count - self.remaining_counts[piece]} 个，剩余 {self.remaining_counts[piece]} 个"
            )
        print("\n")

    def _update_cut_counts(self, pattern: CutPattern):
        """更新剩余需要切割的数量"""
        for piece, count in pattern.pieces:
            self.remaining_counts[piece] -= count

    def print_result(self):
        """打印结果"""
        if not self.patterns:
            print("\n未能生成有效的切割方案!")
            return

        print("\n型材下料方案:")
        print("序号\t材料长度\t下料规格及数量\t余量\t根数")
        for i, pattern in enumerate(self.patterns, 1):
            print(f"{i}\t{pattern}")

        # 按原材料长度统计使用情况
        stock_usage = {}
        total_cost = 0.0  # 总价格
        for pattern in self.patterns:
            length = pattern.stock.length
            if length not in stock_usage:
                stock_usage[length] = 0
            stock_usage[length] += pattern.count
            # 计算总价格
            total_cost += pattern.stock.price * pattern.count

        print("\n原材料使用情况:")
        for length, count in sorted(stock_usage.items()):
            print(f"用长 {length} 的原材 {count} 根")

        # 计算总体利用率
        total_used = sum(
            sum(p.length * c for p, c in pattern.pieces) * pattern.count
            for pattern in self.patterns
        )
        total_stock = sum(
            pattern.stock.length * pattern.count for pattern in self.patterns
        )

        if total_stock > 0:
            utilization = total_used / total_stock * 100
            print(f"\n原材料利用率: {utilization:.2f}%")
        else:
            print("\n警告: 未使用任何原材料!")

        # 打印下料任务的完成情况
        self.print_completion()

        # 计算并打印一共切了多少根
        total_cut = sum(
            sum(count for _, count in pattern.pieces) * pattern.count
            for pattern in self.patterns
        )
        print(f"\n一共切了 {total_cut} 根")

        # 输出总价格
        print(f"\n使用原材料的总价格: {total_cost:.2f}")


def main():
    with open("input.json") as f:
        data = json.load(f)

    solver = CuttingStockSolver(cut_pieces=data["cut_pieces"], stocks=data["stocks"])
    patterns = solver.solve()
    solver.print_result()


if __name__ == "__main__":
    main()
