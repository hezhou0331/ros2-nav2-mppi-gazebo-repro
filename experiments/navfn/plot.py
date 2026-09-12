"""绘制上游 NavFn 实际计算的路径；不模拟机器狗运动。"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

parser=argparse.ArgumentParser()
parser.add_argument('data',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
titles=['Static obstacle: path found','Added obstacle: replanned','Blocked corridor: no path']
for i,ax in enumerate(axes):
    grid=np.genfromtxt(args.data/f'scenario_{i}_grid.csv',delimiter=',',names=True)
    cells=np.zeros((120,180),dtype=int)
    cells[grid['cost'].reshape(120,180)>0]=1
    cells[grid['cost'].reshape(120,180)>=254]=2
    cells[grid['occupied'].reshape(120,180)>0]=3
    ax.imshow(cells,origin='lower',extent=(-.05,17.95,-.05,11.95),cmap=ListedColormap(['#f8fafc','#e7eef5','#b9c7d7','#243447']),vmin=0,vmax=3)
    p=np.genfromtxt(args.data/f'scenario_{i}_path.csv',delimiter=',',names=True)
    if p.size:
        ax.plot(p['x']*.1,p['y']*.1,color='#16a085',lw=2.4,label='Upstream NavFn path')
    ax.scatter([2],[6],s=75,c='#2563eb',marker='o',zorder=4)
    ax.scatter([15.5],[6],s=110,c='#e76f51',marker='*',zorder=4)
    ax.set(title=titles[i],xlabel='x (m)',ylabel='y (m)',xlim=(0,18),ylim=(0,12))
    ax.set_aspect('equal')
fig.suptitle('RoamerX original NavFn | synthetic offline planning test',fontsize=16,fontweight='bold')
fig.supxlabel('Blue: start   Orange: goal   Dark: obstacle   Grey: 0.5 m exclusion margin\nPlanning only; not an M1 hardware or MPPI tracking test.',fontsize=10)
args.output.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(args.output,dpi=160)
print(args.output)
