import java.util.*;
import java.lang.*;
import java.io.*;

class Main
{

	public static int[] tau(int[] a, int n)
	{
		int[] b = new int[n];
		for (int i = 0; i < n; i++)
		{
			b[i] = a[i];
			for (int j = 0; j < i; j++)
				if (a[j] < a[i])
					b[i] = b[i] - 2;
		}
		return b;
	}

	public static void main(String[] args) throws Exception
	{
		File file = new File("output.txt");
		Scanner scan = new Scanner(file);
		String input = scan.nextLine();
		scan.close();
		String[] inputs = input.split(" ");
		//String[] inputs = {"()(()(())())"};

		PrintWriter lines = new PrintWriter("lines.txt");
		PrintWriter evals = new PrintWriter("evaluations.txt");

		for (String str : inputs)
		{
			String[] inputString = new String[3];
			inputString[0] = str;
			evals.print(str + ";");
			String copy = new String(str);
			lines.print(copy + ",");
			int[] index = new int[str.length()];
			for (int i = 0; i < index.length; index[i++] = i);
			boolean flag = false;
			while (!flag)
			{
				if (copy.equals("")) flag = true;
				else
				{
					int i = copy.indexOf("()");
					lines.print("(" + index[i] + "," + index[i+1] + ")");
					if (index.length != 2) lines.print(",");
					copy = copy.substring(0, i) + copy.substring(i+2, copy.length());
					int[] temp = new int[index.length-2];
					for (int j = 0; j < i; j++) temp[j] = index[j];
					for (int j = i; j < index.length - 2; j ++) temp[j] = index[j+2];
					index = temp;
				}		
			}
			lines.println();
			inputString[1] = "";
			for (int i = 0; i < str.length(); i++) inputString[1] += (String.valueOf(i) + " ");
			inputString[1] = inputString[1].substring(0, inputString[1].length() - 1);
			inputString[2] = "";
			String[][] evaluate = new String[36][4]; // hard coded
			int top = 0;
			evaluate[0] = inputString;
			int origLength = inputString[0].length();
			
			while(top != -1)
			{
				if (evaluate[top][0].equals(""))
				{
					String[] popSeq = evaluate[top][2].substring(0, evaluate[top][2].length() - 1).split(" ");
					int n = popSeq.length;
					int[] intPopSeq = new int[n];
					for (int i = 0; i < n; i++) { intPopSeq[i] = Integer.valueOf(popSeq[i]) + 1; }
					intPopSeq = tau(intPopSeq, n);
					evals.print(intPopSeq[0]);
					for (int i = 1; i < n; i++) evals.print("," + intPopSeq[i]);
					evals.print(";");
					top--;
				}
				else
				{
					List<Integer> poppable = new ArrayList<Integer>();
					String pars = evaluate[top][0];
					String indices = evaluate[top][1];
					String[] I = indices.split(" ");
					String pops = evaluate[top][2];
					int popsLength = (pops.equals("")) ? 0 : pops.substring(0, pops.length() - 1).split(" ").length;
					top--;
					int parsLength = pars.length();
					for (int i = 0; i < parsLength - 1; i++)
						if ((pars.substring(i, i+2).equals("()")) & (origLength/2 + popsLength -1 >= Integer.valueOf(I[i])))
							poppable.add(new Integer(i));
					int len = poppable.size();
					for (int j = 0; j < len; j++)
					{
						int i = poppable.get(j);
						String nextPars = pars.substring(0, i) + pars.substring(i+2, parsLength);
						String[] J = indices.split(" ");
						String nextPops = pops + J[i] + " ";
						J[i] = ""; J[i+1] = "";
						String nextIndices = "";
						for (String s : J) if (!s.equals("")) nextIndices += s + " ";
						nextIndices = nextIndices.substring(0, Math.max(nextIndices.length() - 1, 0));
						String[] next = new String[3];
						next[0] = nextPars;
						next[1] = nextIndices;
						next[2] = nextPops;
						evaluate[++top] = next;
					}
				}
			}
			evals.print("\n");
		}
		lines.close();
		evals.close();
	}
}