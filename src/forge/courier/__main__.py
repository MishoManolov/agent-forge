import sys

from .courier import run

team, agent, target = sys.argv[1:4]
run(team, agent, target)
