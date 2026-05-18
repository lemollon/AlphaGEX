const { SlashCommandBuilder, EmbedBuilder } = require('discord.js');

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';

// Brand palette — mirrors frontend/src/index.css @theme tokens.
const BRAND = {
  ACCENT: 0x3b82f6,
  SUCCESS: 0x22c55e,
  DANGER: 0xef4444,
  WARNING: 0xeab308,
};

const mono = (v) => `\`${v}\``;
const dollar = (v) => (v == null ? '--' : mono(`$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`));

module.exports = {
  data: new SlashCommandBuilder()
    .setName('spread')
    .setDescription('Get GEX levels and suggested strikes for a spread')
    .addStringOption((option) =>
      option
        .setName('symbol')
        .setDescription('Underlying symbol (default: SPY)')
        .setRequired(false)
    )
    .addStringOption((option) =>
      option
        .setName('strategy')
        .setDescription('Spread strategy type')
        .setRequired(false)
        .addChoices(
          { name: 'Double Diagonal', value: 'double_diagonal' },
          { name: 'Double Calendar', value: 'double_calendar' },
          { name: 'Iron Condor', value: 'iron_condor' }
        )
    ),

  async execute(interaction) {
    await interaction.deferReply();

    const symbol = interaction.options.getString('symbol') || 'SPY';
    const strategy = interaction.options.getString('strategy') || 'double_diagonal';

    try {
      const gexRes = await fetch(`${API_URL}/api/spreadworks/gex?symbol=${symbol}`);
      if (!gexRes.ok) throw new Error(`GEX fetch failed: ${gexRes.status}`);
      const gexData = await gexRes.json();

      const suggestRes = await fetch(
        `${API_URL}/api/spreadworks/gex-suggest?symbol=${symbol}&strategy=${strategy}`
      );
      if (!suggestRes.ok) throw new Error(`Suggestion fetch failed: ${suggestRes.status}`);
      const suggestion = await suggestRes.json();

      const gexLines = [];
      if (gexData.flip_point) gexLines.push(`Flip · ${dollar(gexData.flip_point)}`);
      if (gexData.call_wall) gexLines.push(`Call Wall · ${dollar(gexData.call_wall)}`);
      if (gexData.put_wall) gexLines.push(`Put Wall · ${dollar(gexData.put_wall)}`);
      if (gexData.gamma_regime) gexLines.push(`Regime · ${mono(gexData.gamma_regime)}`);

      const strikeLines = [];
      if (suggestion.legs) {
        const legs = suggestion.legs;
        if (strategy === 'double_diagonal') {
          strikeLines.push(`Long Put · ${dollar(legs.long_put_strike)}`);
          strikeLines.push(`Short Put · ${dollar(legs.short_put_strike)}`);
          strikeLines.push(`Short Call · ${dollar(legs.short_call_strike)}`);
          strikeLines.push(`Long Call · ${dollar(legs.long_call_strike)}`);
          strikeLines.push(`Short Exp · ${mono(legs.short_expiration)}`);
          strikeLines.push(`Long Exp · ${mono(legs.long_expiration)}`);
        } else if (strategy === 'iron_condor') {
          strikeLines.push(`Long Put · ${dollar(legs.long_put_strike)}`);
          strikeLines.push(`Short Put · ${dollar(legs.short_put_strike)}`);
          strikeLines.push(`Short Call · ${dollar(legs.short_call_strike)}`);
          strikeLines.push(`Long Call · ${dollar(legs.long_call_strike)}`);
          strikeLines.push(`Expiration · ${mono(legs.expiration)}`);
        } else {
          strikeLines.push(`Put Strike · ${dollar(legs.put_strike)}`);
          strikeLines.push(`Call Strike · ${dollar(legs.call_strike)}`);
          strikeLines.push(`Front Exp · ${mono(legs.front_expiration)}`);
          strikeLines.push(`Back Exp · ${mono(legs.back_expiration)}`);
        }
      }

      const strategyLabels = {
        double_diagonal: 'Double Diagonal',
        double_calendar: 'Double Calendar',
        iron_condor: 'Iron Condor',
      };
      const strategyLabel = strategyLabels[strategy] || strategy;

      // Color: green if positive-gamma regime, red if negative, accent otherwise.
      const regime = (gexData.gamma_regime || '').toUpperCase();
      const color = regime === 'POSITIVE' ? BRAND.SUCCESS
        : regime === 'NEGATIVE' ? BRAND.DANGER
        : BRAND.ACCENT;

      const embed = new EmbedBuilder()
        .setTitle(`SpreadWorks · ${symbol} · ${strategyLabel}`)
        .setColor(color)
        .addFields(
          {
            name: 'GEX LEVELS',
            value: gexLines.length > 0 ? gexLines.join('\n') : 'No GEX data available',
            inline: true,
          },
          {
            name: 'SUGGESTED STRIKES',
            value: strikeLines.length > 0 ? strikeLines.join('\n') : 'No suggestion available',
            inline: true,
          }
        )
        .setTimestamp();

      if (suggestion.rationale) {
        embed.addFields({
          name: 'RATIONALE',
          value: suggestion.rationale,
          inline: false,
        });
      }

      if (suggestion.net_debit != null) {
        embed.setFooter({
          text: `Est. Net Debit · $${suggestion.net_debit.toFixed(2)}`,
        });
      }

      await interaction.editReply({ embeds: [embed] });
    } catch (error) {
      console.error('Spread command error:', error);
      await interaction.editReply({
        content: `Failed to fetch spread data for ${symbol}: ${error.message}`,
      });
    }
  },
};
