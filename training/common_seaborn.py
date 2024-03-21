import seaborn as sns

plot_params = {
    "pgf.texsystem": "pdflatex",
    'font.family': 'serif',
    'text.usetex': True,
    'pgf.rcfonts': False,
    "font.size": 7,
    "axes.titlesize": 7,
    "axes.labelsize": 7, 
    "ytick.labelsize": 7, 
    "xtick.labelsize": 7, 
    'legend.fontsize': 7, 
    'legend.title_fontsize': 7,
}
sns_params = {
    'figure.figsize': (7.16, 3),
    'figure.dpi': 300,
    "font.size": 7,
    'figure.titlesize': 7,
    "axes.titlesize": 7,
    "axes.labelsize": 7, 
    "ytick.labelsize": 7, 
    "xtick.labelsize": 7, 
    'xtick.bottom': True,
    'legend.fontsize': 7, 
    'legend.title_fontsize': 7,
    'lines.linewidth': 0.5,
    'patch.edgecolor': 'black',
}
#plot_params['figure.figsize'] = (7.16, 4)
#plot_params['figure.figsize'] = (3.5, 2)
#plot_params['figure.dpi'] = 96
plot_params['figure.dpi'] = 300
#matplotlib.rcParams.update(plot_params)

#sns_params['figure.figsize'] = (7.16, 3)
sns_params['figure.figsize'] = (3.5, 2)
#sns_params['figure.dpi'] = 96
sns_params['figure.dpi'] = 300
sns_params['patch.edgecolor'] = 'black'
sns.set_theme("paper", style='whitegrid', rc=sns_params, color_codes=True, palette='tab10')
#sns.set_context("paper", rc=sns_params)
#sns.set(rc=sns_params)