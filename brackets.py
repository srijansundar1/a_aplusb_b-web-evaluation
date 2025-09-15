import sys

def generate_parentheses(n):
    list =[]

    def dfs(str, open_num, closed_num):
        if open_num == n and closed_num == n:
            list.append("".join(str))
            return

        if open_num < n:
            str.append("(")
            dfs(str, open_num+1, closed_num)
            str.pop()


        if closed_num < open_num:
            str.append(")")
            dfs(str, open_num, closed_num+1)
            str.pop()

    dfs([], 0, 0)
    return list

if __name__ == "__main__":
    n = int(sys.argv[1])
    e = sys.stdout
    f = open('output.txt', 'w')
    sys.stdout = f
    print(*generate_parentheses(n), end='')
    sys.stdout = e
    f.close()